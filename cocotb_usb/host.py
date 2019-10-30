import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.result import TestFailure

from cocotb_usb.descriptors import (Descriptor, getDescriptorRequest,
                                    setAddressRequest, setConfigurationRequest)
from cocotb_usb.usb.pid import PID
from cocotb_usb.usb.endpoint import EndpointType
from cocotb_usb.usb.packet import (wrap_packet, token_packet, data_packet,
                                   sof_packet, handshake_packet)
from cocotb_usb.usb.pp_packet import pp_packet

from cocotb_usb.utils import grouper_tofit, assertEqual


class UsbTest:
    """
    Base class for communicating with a USB test bench.

    Args:
        dut : Object under test as passed by cocotb.
        decouple_clocks (bool, optional): Indicates whether host and device
            share clock signal. If set to False (default), you must provide
            clk48_device clock in test.
    """
    # How long to keep trying when getting NAKs
    RETRY_WAIT = 100  # us
    MAX_RETRIES = 10

    def __init__(self, dut, **kwargs):
        decouple_clocks = kwargs.get('decouple_clocks', False)
        self.dut = dut
        self.clock_period = 20830
        cocotb.fork(Clock(dut.clk48_host, self.clock_period, 'ps').start())
        if not decouple_clocks:
            cocotb.fork(
                Clock(dut.clk48_device, self.clock_period, 'ps').start())

        self.dut.usb_d_p = 0
        self.dut.usb_d_n = 0
        # Set the signal "test_name" to match this test
        import inspect
        tn = cocotb.binary.BinaryValue(value=None, n_bits=4096)
        tn.buff = inspect.stack()[2][3]
        self.dut.test_name = tn

    @cocotb.coroutine
    def reset(self):
        """Reset DUT."""
        self.dut.reset = 1
        self.dut.usb_d_p = 1
        self.dut.usb_d_n = 0
        self.address = 0

        yield ClockCycles(self.dut.clk48_host, 10, rising=True)
        self.dut.reset = 0
        yield ClockCycles(self.dut.clk48_host, 10, rising=True)

    @cocotb.coroutine
    def port_reset(self, time=50e3):
        """Send USB port reset - SE0 condition for at least 50 ms
        (on root port).

        Args:
            time (int): Duration of reset in us.
        """
        self.dut._log.debug("Resetting port for {} us".format(time))
        self.dut.usb_d_p = 0
        self.dut.usb_d_n = 0
        yield Timer(time, units="us")

    @cocotb.coroutine
    def connect(self):
        """Simulate FS connect to DUT  - DP pulled high."""
        # FS connect - DP pulled high
        self.dut.usb_d_p = 1
        self.dut.usb_d_n = 0
        yield ClockCycles(self.dut.clk48_host, 10)

    @cocotb.coroutine
    def disconnect(self):
        """Simulate device disconnect, both lines pulled low."""
        # Detached - pulldowns on host side
        self.dut.usb_d_p = 0
        self.dut.usb_d_n = 0
        yield ClockCycles(self.dut.clk48_host, 10)
        # Device address should have reset
        self.address = 0

    def print_ep(self, epaddr, msg, *args):
        self.dut._log.info("ep(%i, %s): %s" %
                           (EndpointType.epnum(epaddr),
                            EndpointType.epdir(epaddr).name, msg) % args)

    # Host->Device
    @cocotb.coroutine
    def _host_send_packet(self, packet):
        """Send a USB packet."""

        # Packet gets multiplied by 4x so we can send using the
        # usb48 clock instead of the usb12 clock.
        packet = 'JJJJJJJJ' + wrap_packet(packet)
        assertEqual('J', packet[-1], "Packet didn't end in J: " + packet)

        for v in packet:
            if v == '0' or v == '_':
                # SE0 - both lines pulled low
                self.dut.usb_d_p <= 0
                self.dut.usb_d_n <= 0
            elif v == '1':
                # SE1 - illegal, should never occur
                self.dut.usb_d_p <= 1
                self.dut.usb_d_n <= 1
            elif v == '-' or v == 'I':
                # Idle
                self.dut.usb_d_p <= 1
                self.dut.usb_d_n <= 0
            elif v == 'J':
                self.dut.usb_d_p <= 1
                self.dut.usb_d_n <= 0
            elif v == 'K':
                self.dut.usb_d_p <= 0
                self.dut.usb_d_n <= 1
            else:
                raise TestFailure("Unknown value: %s" % v)
            yield RisingEdge(self.dut.clk48_host)

    @cocotb.coroutine
    def host_send_token_packet(self, pid, addr, ep):
        epnum = EndpointType.epnum(ep)
        yield self._host_send_packet(token_packet(pid, addr, epnum))

    @cocotb.coroutine
    def host_send_data_packet(self, pid, data):
        assert pid in (PID.DATA0, PID.DATA1), pid
        yield self._host_send_packet(data_packet(pid, data))

    @cocotb.coroutine
    def host_send_sof(self, time):
        yield self._host_send_packet(sof_packet(time))

    @cocotb.coroutine
    def host_send_ack(self):
        yield self._host_send_packet(handshake_packet(PID.ACK))

    @cocotb.coroutine
    def host_send(self, data01, addr, epnum, data, expected=PID.ACK):
        """Send data out the virtual USB connection, including an OUT token."""
        self.retries = self.MAX_RETRIES
        while self.retries:
            yield self.host_send_token_packet(PID.OUT, addr, epnum)
            yield self.host_send_data_packet(data01, data)
            yield self.host_expect_packet(handshake_packet(expected),
                                          "Expected {} packet."
                                          .format(expected))

    @cocotb.coroutine
    def host_setup(self, addr, epnum, data):
        """Send data out the virtual USB connection, including a SETUP
        token.
        """
        self.retries = self.MAX_RETRIES
        while self.retries:
            yield self.host_send_token_packet(PID.SETUP, addr, epnum)
            yield self.host_send_data_packet(PID.DATA0, data)
            yield self.host_expect_ack()

    @cocotb.coroutine
    def host_recv(self, data01, addr, epnum, data):
        """Send data out the virtual USB connection, including an IN token."""
        self.retries = self.MAX_RETRIES
        while self.retries:
            yield Timer(self.RETRY_WAIT, "us")
            yield self.host_send_token_packet(PID.IN, addr, epnum)
            yield self.host_expect_data_packet(data01, data)
        yield self.host_send_ack()

    # Device->Host
    @cocotb.coroutine
    def host_expect_packet(self, packet, msg=None):
        """Expect to receive the following USB packet.

        Args:
            packet: Values to be received as list of bytes.
            msg (str, optional): Message to be printed on mismatch.
        """
        def current():
            values = (self.dut.usb_d_p, self.dut.usb_d_n)

            if values == (0, 0):
                return '_'
            elif values == (1, 1):
                return '1'
            elif values == (1, 0):
                return 'J'
            elif values == (0, 1):
                return 'K'
            else:
                raise TestFailure("Unrecognized dut values: {}".format(values))

        # We want to sample in the middle of a signal to allow for jitter
        t_middle = Timer(self.clock_period // 4, 'ps')
        # Wait for transmission to start
        tx = 0
        bit_times = 0
        for i in range(0, 100):
            tx = self.dut.usb_tx_en
            if tx == 1:
                break
            yield RisingEdge(self.dut.clk48_host)
            yield t_middle
            bit_times = bit_times + 1
        if tx != 1:
            raise TestFailure("No packet started, " + msg)

        # USB specifies that the turn-around time is 7.5 bit times
        # for the device
        bit_time_max = 12.5
        bit_time_acceptable = 7.5
        if (bit_times / 4.0) > bit_time_max:
            raise TestFailure(
                "Response came after {} bit times, which is more than {}".
                format(bit_times / 4.0, bit_time_max))
        if (bit_times / 4.0) > bit_time_acceptable:
            self.dut._log.warn(
                "Response came after {} bit times (> {})".format(
                    bit_times / 4.0, bit_time_acceptable))
        else:
            self.dut._log.info("Response came after {} bit times".format(
                bit_times / 4.0))

        # Read in the transmission data
        result = ""
        for i in range(0, 4096):
            if self.dut.usb_tx_en != 1:
                break
            else:
                result += current()
            yield RisingEdge(self.dut.clk48_host)
            yield t_middle
        if tx == 1:
            raise TestFailure("Packet didn't finish, " + msg)
        self.dut.usb_d_p = 1
        self.dut.usb_d_n = 0

        # Check the packet received matches
        expected = pp_packet(wrap_packet(packet))
        actual = pp_packet(result)
        nak = pp_packet(wrap_packet(handshake_packet(PID.NAK)))
        if (actual == nak) and (expected != nak) and self.retries >= 2:
            self.retries -= 1
            self.dut._log.info("Got NAK, retrying "
                               "({} attempts left)".format(self.retries))
            yield Timer(self.RETRY_WAIT, 'us')
            return
        else:
            self.retries = 0
            assertEqual(expected, actual, msg)

    @cocotb.coroutine
    def host_expect_ack(self):
        """Expect an ACK packet."""
        yield self.host_expect_packet(handshake_packet(PID.ACK),
                                      "Expected ACK packet.")

    @cocotb.coroutine
    def host_expect_nak(self):
        """Expect a NAK packet."""
        yield self.host_expect_packet(handshake_packet(PID.NAK),
                                      "Expected NAK packet.")

    @cocotb.coroutine
    def host_expect_stall(self):
        """Expect a STALL packet."""
        yield self.host_expect_packet(handshake_packet(PID.STALL),
                                      "Expected STALL packet.")

    @cocotb.coroutine
    def host_expect_data_packet(self, pid, data):
        """Expect to receive a data packet.

        Args:
            pid: Either ``PID.DATA0`` or ``PID.DATA1``.
            data: Expected values as list of bytes.
        """
        assert pid in (PID.DATA0, PID.DATA1), pid
        yield self.host_expect_packet(
            data_packet(pid, data),
            "Expected %s packet with %r" % (pid.name, data))

    @cocotb.coroutine
    def transaction_setup(self, addr, data, epnum=0):
        xmit = cocotb.fork(self.host_setup(addr, epnum, data))
        yield xmit.join()

    @cocotb.coroutine
    def transaction_data_out(self,
                             addr,
                             ep,
                             data,
                             chunk_size=64,
                             expected=PID.ACK):
        epnum = EndpointType.epnum(ep)
        datax = PID.DATA1

        for _i, chunk in enumerate(grouper_tofit(chunk_size, data)):
            self.dut._log.warning("Sending {} bytes to device".format(
                len(chunk)))
            xmit = cocotb.fork(
                self.host_send(datax, addr, epnum, chunk, expected))
            yield xmit.join()

    @cocotb.coroutine
    def transaction_data_in(self, addr, ep, data, chunk_size=64):
        epnum = EndpointType.epnum(ep)
        datax = PID.DATA1
        sent_data = 0
        for i, chunk in enumerate(grouper_tofit(chunk_size, data)):
            self.dut._log.debug("Expecting chunk {}".format(i))
            sent_data = 1
            self.dut._log.debug(
                "Actual data we're expecting: {}".format(chunk))

            recv = cocotb.fork(self.host_recv(datax, addr, epnum, chunk))
            yield recv.join()

            if datax == PID.DATA0:
                datax = PID.DATA1
            else:
                datax = PID.DATA0

        if not sent_data:
            recv = cocotb.fork(self.host_recv(datax, addr, epnum, []))
            yield recv.join()

    @cocotb.coroutine
    def transaction_status_in(self, addr, ep):
        epnum = EndpointType.epnum(ep)
        assert EndpointType.epdir(ep) == EndpointType.IN
        xmit = cocotb.fork(self.host_recv(PID.DATA1, addr, epnum, []))
        yield xmit.join()

    @cocotb.coroutine
    def transaction_status_out(self, addr, ep):
        epnum = EndpointType.epnum(ep)
        assert EndpointType.epdir(ep) == EndpointType.OUT
        xmit = cocotb.fork(self.host_send(PID.DATA1, addr, epnum, []))
        yield xmit.join()

    @cocotb.coroutine
    def control_transfer_out(self, addr, setup_data, descriptor_data=None):
        """Perform an OUT control transfer.

        Args:
            addr (int): Device address.
            setup_data: Request to be sent, as list of bytes.
            descriptor_data (optional): Data to be sent, as list of bytes.
        """
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        # Data sanity check
        if (setup_data[0] & 0x80) == 0x80:
            raise Exception(
                "setup_data indicated an IN transfer, but you requested"
                "an OUT transfer"
            )
        if (setup_data[7] != 0
                or setup_data[6] != 0) and descriptor_data is None:
            raise Exception(
                "setup_data indicates data, but no descriptor data"
                "was specified"
            )
        if (setup_data[7] == 0
                and setup_data[6] == 0) and descriptor_data is not None:
            raise Exception(
                "setup_data indicates no data, but descriptor data"
                "was specified"
            )

        # Setup stage
        self.dut._log.info("setup stage")
        yield self.transaction_setup(addr, setup_data)

        # Data stage
        if descriptor_data is not None:
            self.dut._log.info("data stage")
            yield self.transaction_data_out(addr, epaddr_out, descriptor_data)
        if descriptor_data is not None:
            yield RisingEdge(self.dut.clk48_host)

        # Status stage
        self.dut._log.info("status stage")

        yield self.transaction_status_in(addr, epaddr_in)
        yield RisingEdge(self.dut.clk48_host)

    @cocotb.coroutine
    def control_transfer_in(self, addr, setup_data, descriptor_data=None):
        """Perform an IN control transfer.

        Args:
            addr (int): Device address.
            setup_data: Request to be sent, as list of bytes.
            descriptor_data (optional): Data expected to be received, as list
                of bytes.
        """
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        # Data sanity check
        if (setup_data[0] & 0x80) == 0x00:
            raise Exception(
                "setup_data indicated an OUT transfer, but you requested"
                "an IN transfer"
            )
        if (setup_data[7] != 0
                or setup_data[6] != 0) and descriptor_data is None:
            raise Exception(
                "setup_data indicates data, but no descriptor data"
                "was specified"
            )
        if (setup_data[7] == 0
                and setup_data[6] == 0) and descriptor_data is not None:
            raise Exception(
                "setup_data indicates no data, but descriptor data"
                "was specified"
            )

        # Setup stage
        self.dut._log.info("setup stage")
        yield self.transaction_setup(addr, setup_data)

        # Data stage
        if descriptor_data is not None:
            self.dut._log.info("data stage")
            yield self.transaction_data_in(addr, epaddr_in, descriptor_data)

        # Give the signal one clock cycle to perccolate through
        # the event manager
        yield RisingEdge(self.dut.clk48_host)

        # Status stage
        self.dut._log.info("status stage")
        yield self.transaction_status_out(addr, epaddr_out)
        yield RisingEdge(self.dut.clk48_host)

    @cocotb.coroutine
    def set_device_address(self, address):
        """Set USB device address.

        Args:
            address (int): Value to be set.
        """
        self.dut._log.debug("Setting device address")
        yield self.control_transfer_out(
            self.address,
            setAddressRequest(address),
            None,
        )
        self.address = address

    @cocotb.coroutine
    def get_device_descriptor(self, response, length=18):
        """Read the device descriptor from DUT.

        Args:
            response: Expected descriptor contents as list of bytes.
        """
        self.dut._log.debug("Getting device descriptor")
        request = getDescriptorRequest(descriptor_type=Descriptor.Types.DEVICE,
                                       descriptor_index=0,
                                       lang_id=Descriptor.LangId.UNSPECIFIED,
                                       length=length)
        yield self.control_transfer_in(self.address, request, response)

    @cocotb.coroutine
    def get_configuration_descriptor(self, length, response):
        """Read a configuration descriptor from DUT.

        Args:
            length (int): Number of bytes to be read.
            response: Expected descriptor contents as list of bytes.
        """
        self.dut._log.debug("Getting config descriptor")
        request = getDescriptorRequest(
            descriptor_type=Descriptor.Types.CONFIGURATION,
            descriptor_index=0,
            lang_id=Descriptor.LangId.UNSPECIFIED,
            length=length)

        yield self.control_transfer_in(self.address, request, response)

    @cocotb.coroutine
    def get_string_descriptor(self, lang_id, idx, response):
        """Read a string descriptor from DUT.

        Args:
            lang_id (int): Language ID of descriptor.
            idx (int): Descriptor index.
            response: Expected descriptor contents as list of bytes.
        """
        self.dut._log.debug("Getting string descriptor")
        request = getDescriptorRequest(descriptor_type=Descriptor.Types.STRING,
                                       descriptor_index=idx,
                                       lang_id=lang_id,
                                       length=255)

        yield self.control_transfer_in(self.address, request, response)

    @cocotb.coroutine
    def get_device_qualifier(self, length, response):
        """Read a device qualifier descriptor from DUT.

        Args:
            length (int): Number of bytes to be read.
            response: Expected descriptor contents as list of bytes.
        """
        self.dut._log.debug("Getting device qualifier descriptor")
        request = getDescriptorRequest(
            descriptor_type=Descriptor.Types.DEVICE_QUALIFIER,
            descriptor_index=0,
            lang_id=Descriptor.LangId.UNSPECIFIED,
            length=length)

        yield self.control_transfer_in(self.address, request, response)

    @cocotb.coroutine
    def set_configuration(self, idx):
        """Send a SET_CONFIGURATION standard device request to DUT.

        Args:
            idx (int): Configuration number to be set.
        """
        request = setConfigurationRequest(idx)

        self.dut._log.debug("Setting device configuration")
        yield self.control_transfer_out(
            self.address,
            request,
            None,
        )
