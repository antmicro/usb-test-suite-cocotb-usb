import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, NullTrigger, Timer, ClockCycles
from cocotb.result import TestFailure, TestSuccess, ReturnValue

from .usb.descriptors import *
from .usb.pid import *
from .usb.endpoint import *
from .usb.packet import *
from .usb.pprint import pp_packet

from .utils import *

# Litex imports
from wishbone import WishboneMaster, WBOp

class UsbTest:
    """
    Base class for communicating with a USB test bench

    Args:
        dut : Object under test as passed by cocotb.
        decouple_clocks (bool, optional): Indicates whether host and device share
            clock signal. If set to False, you must provide clk48_device clock in test.
    """
    def __init__(self, dut, **kwargs):
        decouple_clocks = kwargs.get('decouple_clocks', False)
        self.dut = dut
        self.clock_period = 20830
        cocotb.fork(Clock(dut.clk48_host, self.clock_period, 'ps').start())
        if not decouple_clocks:
            cocotb.fork(Clock(dut.clk48_device, self.clock_period, 'ps').start())

        self.dut.usb_d_p = 0
        self.dut.usb_d_n = 0
        # Set the signal "test_name" to match this test
        import inspect
        tn = cocotb.binary.BinaryValue(value=None, n_bits=4096)
        tn.buff = inspect.stack()[2][3]
        self.dut.test_name = tn

    @cocotb.coroutine
    def reset(self):
        """Reset DUT"""
        self.dut.reset = 1
        self.dut.usb_d_p = 1
        self.dut.usb_d_n = 0
        self.address = 0

        yield ClockCycles(self.dut.clk48_host,10,rising=True)
        self.dut.reset = 0
        yield ClockCycles(self.dut.clk48_host,10,rising=True)

    @cocotb.coroutine
    def connect(self):
        """Simulate FS connect to DUT"""
        # FS connect - DP pulled high
        self.dut.usb_d_p = 1
        self.dut.usb_d_n = 0
        yield ClockCycles(self.dut.clk48_host, 10)

    @cocotb.coroutine
    def disconnect(self):
        """Simulate device disconnect, both lines pulled low"""
        # Detached - pulldowns on host side
        self.dut.usb_d_p = 0
        self.dut.usb_d_n = 0
        yield ClockCycles(self.dut.clk48_host, 10)
        # Device address should have reset
        self.address = 0

    def assertEqual(self, a, b, msg):
        if a != b:
            raise TestFailure("{} != {} - {}".format(a, b, msg))

    def assertSequenceEqual(self, a, b, msg):
        if a != b:
            raise TestFailure("{} vs {} - {}".format(a, b, msg))

    def print_ep(self, epaddr, msg, *args):
        self.dut._log.info("ep(%i, %s): %s" % (
            EndpointType.epnum(epaddr),
            EndpointType.epdir(epaddr).name,
            msg) % args)

    # Host->Device
    @cocotb.coroutine
    def _host_send_packet(self, packet):
        """Send a USB packet."""

        # Packet gets multiplied by 4x so we can send using the
        # usb48 clock instead of the usb12 clock.
        packet = 'JJJJJJJJ' + wrap_packet(packet)
        self.assertEqual('J', packet[-1], "Packet didn't end in J: "+packet)

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
        """Send data out the virtual USB connection, including an OUT token"""
        yield self.host_send_token_packet(PID.OUT, addr, epnum)
        yield self.host_send_data_packet(data01, data)
        yield self.host_expect_packet(handshake_packet(expected), "Expected {} packet.".format(expected))

    @cocotb.coroutine
    def host_setup(self, addr, epnum, data):
        """Send data out the virtual USB connection, including a SETUP token"""
        yield self.host_send_token_packet(PID.SETUP, addr, epnum)
        yield self.host_send_data_packet(PID.DATA0, data)
        yield self.host_expect_ack()

    @cocotb.coroutine
    def host_recv(self, data01, addr, epnum, data):
        """Send data out the virtual USB connection, including an IN token"""
        yield self.host_send_token_packet(PID.IN, addr, epnum)
        yield self.host_expect_data_packet(data01, data)
        yield self.host_send_ack()

    # Device->Host
    @cocotb.coroutine
    def host_expect_packet(self, packet, msg=None):
        """Expect to receive the following USB packet."""

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
        t_middle = Timer(self.clock_period//4, 'ps')
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

        # # USB specifies that the turn-around time is 7.5 bit times for the device
        bit_time_max = 12.5
        bit_time_acceptable = 7.5
        if (bit_times/4.0) > bit_time_max:
            raise TestFailure("Response came after {} bit times, which is more than {}".format(bit_times / 4.0, bit_time_max))
        if (bit_times/4.0) > bit_time_acceptable:
            self.dut._log.warn("Response came after {} bit times (> {})".format(bit_times / 4.0, bit_time_acceptable))
        else:
            self.dut._log.info("Response came after {} bit times".format(bit_times / 4.0))

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
        self.assertSequenceEqual(expected, actual, msg)

    @cocotb.coroutine
    def host_expect_ack(self):
        yield self.host_expect_packet(handshake_packet(PID.ACK), "Expected ACK packet.")

    @cocotb.coroutine
    def host_expect_nak(self):
        yield self.host_expect_packet(handshake_packet(PID.NAK), "Expected NAK packet.")

    @cocotb.coroutine
    def host_expect_stall(self):
        yield self.host_expect_packet(handshake_packet(PID.STALL), "Expected STALL packet.")

    @cocotb.coroutine
    def host_expect_data_packet(self, pid, data):
        assert pid in (PID.DATA0, PID.DATA1), pid
        yield self.host_expect_packet(data_packet(pid, data), "Expected %s packet with %r" % (pid.name, data))

    @cocotb.coroutine
    def transaction_setup(self, addr, data, epnum=0):
        xmit = cocotb.fork(self.host_setup(addr, epnum, data))
        yield xmit.join()

    @cocotb.coroutine
    def transaction_data_out(self, addr, ep, data, chunk_size=64, expected=PID.ACK):
        epnum = EndpointType.epnum(ep)
        datax = PID.DATA1

        for _i, chunk in enumerate(grouper_tofit(chunk_size, data)):
            self.dut._log.warning("Sending {} bytes to device".format(len(chunk)))
            xmit = cocotb.fork(self.host_send(datax, addr, epnum, chunk, expected))
            yield xmit.join()

    @cocotb.coroutine
    def transaction_data_in(self, addr, ep, data, chunk_size=64):
        epnum = EndpointType.epnum(ep)
        datax = PID.DATA1
        sent_data = 0
        for i, chunk in enumerate(grouper_tofit(chunk_size, data)):
            sent_data = 1
            self.dut._log.debug("Actual data we're expecting: {}".format(chunk))

            recv = cocotb.fork(self.host_recv(datax, addr, epnum, chunk))
            yield recv.join()

            if datax == PID.DATA0:
                datax = PID.DATA1

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
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        # Data sanity check
        if (setup_data[0] & 0x80) == 0x80:
            raise Exception("setup_data indicated an IN transfer, but you requested an OUT transfer")
        if (setup_data[7] != 0 or setup_data[6] != 0) and descriptor_data is None:
            raise Exception("setup_data indicates data, but no descriptor data was specified")
        if (setup_data[7] == 0 and setup_data[6] == 0) and descriptor_data is not None:
            raise Exception("setup_data indicates no data, but descriptor data was specified")

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
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        # Data sanity check
        if (setup_data[0] & 0x80) == 0x00:
            raise Exception("setup_data indicated an OUT transfer, but you requested an IN transfer")
        if (setup_data[7] != 0 or setup_data[6] != 0) and descriptor_data is None:
            raise Exception("setup_data indicates data, but no descriptor data was specified")
        if (setup_data[7] == 0 and setup_data[6] == 0) and descriptor_data is not None:
            raise Exception("setup_data indicates no data, but descriptor data was specified")

        # Setup stage
        self.dut._log.info("setup stage")
        yield self.transaction_setup(addr, setup_data)

        # Data stage
        if descriptor_data is not None:
            self.dut._log.info("data stage")
            yield self.transaction_data_in(addr, epaddr_in, descriptor_data)

        # Give the signal one clock cycle to perccolate through the event manager
        yield RisingEdge(self.dut.clk48_host)

        # Status stage
        self.dut._log.info("status stage")
        yield self.transaction_status_out(addr, epaddr_out)
        yield RisingEdge(self.dut.clk48_host)

    @cocotb.coroutine
    def set_device_address(self, address):
        """Set USB device address

        Args:
            address (int): Value to be set.
        """
        yield self.control_transfer_out(
            self.address,
            setAddressRequest(address),
            None,
        )
        self.address = address

    @cocotb.coroutine
    def get_device_descriptor(self, response):
        """Read the device descriptor from DUT.

        Args:
            response: Expected descriptor contents as list of bytes.
        """
        request = getDescriptorRequest(descriptor_type = Descriptor.Types.DEVICE,
            descriptor_index = 0,
            lang_id = Descriptor.LangId.UNSPECIFIED,
            length = 18)
        yield self.control_transfer_in(self.address, request, response)

    @cocotb.coroutine
    def get_configuration_descriptor(self, length, response):
        """Read a configuration descriptor from DUT.

        Args:
            length (int): Number of bytes to be read.
            response: Expected descriptor contents as list of bytes.
        """
        request = getDescriptorRequest(descriptor_type = Descriptor.Types.CONFIGURATION,
                descriptor_index = 0,
                lang_id = Descriptor.LangId.UNSPECIFIED,
                length = length)

        yield self.control_transfer_in(
            self.address,
            request,
            response
        )

    @cocotb.coroutine
    def get_string_descriptor(self, lang_id, idx, response):
        """Read a string descriptor from DUT.

        Args:
            lang_id (int): Language ID of descriptor.
            idx (int): Descriptor index.
            response: Expected descriptor contents as list of bytes.
        """
        request = getDescriptorRequest(descriptor_type = Descriptor.Types.STRING,
                descriptor_index = idx,
                lang_id = lang_id,
                length = 255)

        yield self.control_transfer_in(
            self.address,
            request,
            response
        )

    @cocotb.coroutine
    def set_configuration(self, idx):
        """Send a SET_CONFIGURATION standard device request to DUT

        Args:
            idx (int): Configuration number to be set.
        """
        request = setConfigurationRequest(idx)

        yield self.control_transfer_out(
            self.address,
            request,
            None,
        )

class UsbTestValenty(UsbTest):
    """Class for testing ValentyUSB IP core.
    Includes functions to communicate and generate responses without a CPU,
    making use of a Wishbone bridge

    Args:
        dut : Object under test as passed by cocotb.
        csr_file (str): CSV file containing CSR register addresses, generated by Litex.
        decouple_clocks (bool, optional): Indicates whether host and device share
            clock signal. If set to False, you must provide clk48_device clock in test.
    """
    def __init__(self, dut, csr_file, **kwargs):
        super().__init__(dut, **kwargs)
        self.csrs = dict()
        self.csrs = parse_csr(csr_file)
        self.wb = WishboneMaster(dut, "wishbone", dut.clk12, timeout=20)

    @cocotb.coroutine
    def reset(self):
        yield super().reset()

        # Enable endpoint 0
        yield self.write(self.csrs['usb_enable_out0'], 0xff)
        yield self.write(self.csrs['usb_enable_out1'], 0xff)
        yield self.write(self.csrs['usb_enable_in0'], 0xff)
        yield self.write(self.csrs['usb_enable_in1'], 0xff)
        yield self.write(self.csrs['usb_setup_ev_enable'], 0xff)
        yield self.write(self.csrs['usb_in_ev_enable'], 0xff)
        yield self.write(self.csrs['usb_out_ev_enable'], 0xff)

        yield self.write(self.csrs['usb_setup_ev_pending'], 0xff)
        yield self.write(self.csrs['usb_in_ev_pending'], 0xff)
        yield self.write(self.csrs['usb_out_ev_pending'], 0xff)
        yield self.write(self.csrs['usb_address'], 0)

    @cocotb.coroutine
    def write(self, addr, val):
        yield self.wb.write(addr, val)

    @cocotb.coroutine
    def read(self, addr):
        value = yield self.wb.read(addr)
        raise ReturnValue(value)

    @cocotb.coroutine
    def connect(self):
        USB_PULLUP_OUT = self.csrs['usb_pullup_out']
        yield self.write(USB_PULLUP_OUT, 1)

    @cocotb.coroutine
    def clear_pending(self, _ep):
        yield Timer(0)

    @cocotb.coroutine
    def disconnect(self):
        super().disconnect()
        USB_PULLUP_OUT = self.csrs['usb_pullup_out']
        self.address = 0
        yield self.write(USB_PULLUP_OUT, 0)

    @cocotb.coroutine
    def pending(self, ep):
        if EndpointType.epdir(ep) == EndpointType.IN:
            val = yield self.read(self.csrs['usb_in_status'])
        else:
            val = yield self.read(self.csrs['usb_out_status'])
        raise ReturnValue(val & 1)

    @cocotb.coroutine
    def expect_setup(self, epaddr, expected_data):
        actual_data = []
        # wait for data to appear
        for i in range(128):
            self.dut._log.debug("Prime loop {}".format(i))
            status = yield self.read(self.csrs['usb_setup_status'])
            have = status & 1
            if have:
                break
            yield RisingEdge(self.dut.clk12)

        for i in range(48):
            self.dut._log.debug("Read loop {}".format(i))
            status = yield self.read(self.csrs['usb_setup_status'])
            have = status & 1
            if not have:
                break
            v = yield self.read(self.csrs['usb_setup_data'])
            yield self.write(self.csrs['usb_setup_ctrl'], 1)
            actual_data.append(v)
            yield RisingEdge(self.dut.clk12)

        if len(actual_data) < 2:
            raise TestFailure("data was short (got {}, expected {})".format(expected_data, actual_data))
        actual_data, actual_crc16 = actual_data[:-2], actual_data[-2:]

        self.print_ep(epaddr, "Got: %r (expected: %r)", actual_data, expected_data)
        self.assertSequenceEqual(expected_data, actual_data, "SETUP packet not received")
        self.assertSequenceEqual(crc16(expected_data), actual_crc16, "CRC16 not valid")

    @cocotb.coroutine
    def drain_setup(self):
        actual_data = []
        for i in range(48):
            status = yield self.read(self.csrs['usb_setup_status'])
            have = status & 1
            if not have:
                break
            v = yield self.read(self.csrs['usb_setup_data'])
            yield self.write(self.csrs['usb_setup_ctrl'], 1)
            actual_data.append(v)
            yield RisingEdge(self.dut.clk12)
        return actual_data

    @cocotb.coroutine
    def drain_out(self):
        actual_data = []
        for i in range(48):
            status = yield self.read(self.csrs['usb_out_status'])
            have = status & 1
            if not have:
                break
            v = yield self.read(self.csrs['usb_out_data'])
            yield self.write(self.csrs['usb_out_ctrl'], 1)
            actual_data.append(v)
            yield RisingEdge(self.dut.clk12)
        return actual_data

    @cocotb.coroutine
    def expect_data(self, epaddr, expected_data, expected):
        actual_data = []
        # wait for data to appear
        for i in range(128):
            self.dut._log.debug("Prime loop {}".format(i))
            status = yield self.read(self.csrs['usb_out_status'])
            have = status & 1
            if have:
                break
            yield RisingEdge(self.dut.clk12)

        for i in range(256):
            self.dut._log.debug("Read loop {}".format(i))
            status = yield self.read(self.csrs['usb_out_status'])
            have = status & 1
            if not have:
                break
            v = yield self.read(self.csrs['usb_out_data'])
            yield self.write(self.csrs['usb_out_ctrl'], 3)
            actual_data.append(v)
            yield RisingEdge(self.dut.clk12)

        if expected == PID.ACK:
            if len(actual_data) < 2:
                raise TestFailure("data {} was short".format(actual_data))
            actual_data, actual_crc16 = actual_data[:-2], actual_data[-2:]

            self.print_ep(epaddr, "Got: %r (expected: %r)", actual_data, expected_data)
            self.assertSequenceEqual(expected_data, actual_data, "DATA packet not correctly received")
            self.assertSequenceEqual(crc16(expected_data), actual_crc16, "CRC16 not valid")

    @cocotb.coroutine
    def set_response(self, ep, response):
        if EndpointType.epdir(ep) == EndpointType.IN and response == EndpointResponse.ACK:
            yield self.write(self.csrs['usb_in_ctrl'], EndpointType.epnum(ep))

    @cocotb.coroutine
    def send_data(self, token, ep, data):
        for b in data:
            yield self.write(self.csrs['usb_in_data'], b)
        yield self.write(self.csrs['usb_in_ctrl'], ep)

    @cocotb.coroutine
    def transaction_setup(self, addr, data, epnum=0):
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        xmit = cocotb.fork(self.host_setup(addr, epnum, data))
        yield self.expect_setup(epaddr_out, data)
        yield xmit.join()

    @cocotb.coroutine
    def transaction_data_out(self, addr, ep, data, chunk_size=64, expected=PID.ACK):
        epnum = EndpointType.epnum(ep)
        datax = PID.DATA1

        # # Set it up so we ACK the final IN packet
        # yield self.write(self.csrs['usb_in_ctrl'], 0)
        for _i, chunk in enumerate(grouper_tofit(chunk_size, data)):
            self.dut._log.warning("Sening {} bytes to host".format(len(chunk)))
            # Enable receiving data
            yield self.write(self.csrs['usb_out_ctrl'], (1 << 1))
            xmit = cocotb.fork(self.host_send(datax, addr, epnum, chunk, expected))
            yield self.expect_data(epnum, list(chunk), expected)
            yield xmit.join()

            if datax == PID.DATA0:
                datax = PID.DATA1
            else:
                datax = PID.DATA0

    @cocotb.coroutine
    def transaction_data_in(self, addr, ep, data, chunk_size=64):
        epnum = EndpointType.epnum(ep)
        datax = PID.DATA1
        sent_data = 0
        for i, chunk in enumerate(grouper_tofit(chunk_size, data)):
            sent_data = 1
            self.dut._log.debug("Actual data we're expecting: {}".format(chunk))
            for b in chunk:
                yield self.write(self.csrs['usb_in_data'], b)
            yield self.write(self.csrs['usb_in_ctrl'], epnum)
            recv = cocotb.fork(self.host_recv(datax, addr, epnum, chunk))
            yield recv.join()

            if datax == PID.DATA0:
                datax = PID.DATA1
            else:
                datax = PID.DATA0
        if not sent_data:
            yield self.write(self.csrs['usb_in_ctrl'], epnum)
            recv = cocotb.fork(self.host_recv(datax, addr, epnum, []))
            yield self.send_data(datax, epnum, data)
            yield recv.join()

    @cocotb.coroutine
    def set_data(self, ep, data):
        _epnum = EndpointType.epnum(ep)
        for b in data:
            yield self.write(self.csrs['usb_in_data'], b)

    @cocotb.coroutine
    def control_transfer_out(self, addr, setup_data, descriptor_data=None):
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        if (setup_data[0] & 0x80) == 0x80:
            raise Exception("setup_data indicated an IN transfer, but you requested an OUT transfer")

        setup_ev = yield self.read(self.csrs['usb_setup_ev_pending'])
        if setup_ev != 0:
            raise TestFailure("setup_ev should be 0 at the start of the test, was: {:02x}".format(setup_ev))

        # Setup stage
        self.dut._log.info("setup stage")
        yield self.transaction_setup(addr, setup_data)

        setup_ev = yield self.read(self.csrs['usb_setup_ev_pending'])
        if setup_ev != 1:
            raise TestFailure("setup_ev should be 1, was: {:02x}".format(setup_ev))
        yield self.write(self.csrs['usb_setup_ev_pending'], setup_ev)

        # Data stage
        if descriptor_data is not None:
            out_ev = yield self.read(self.csrs['usb_out_ev_pending'])
            if out_ev != 0:
                raise TestFailure("out_ev should be 0 at the start of the test, was: {:02x}".format(out_ev))
        if (setup_data[7] != 0 or setup_data[6] != 0) and descriptor_data is None:
            raise Exception("setup_data indicates data, but no descriptor data was specified")
        if (setup_data[7] == 0 and setup_data[6] == 0) and descriptor_data is not None:
            raise Exception("setup_data indicates no data, but descriptor data was specified")
        if descriptor_data is not None:
            self.dut._log.info("data stage")
            yield self.transaction_data_out(addr, epaddr_out, descriptor_data)
        if descriptor_data is not None:
            yield RisingEdge(self.dut.clk12)
            out_ev = yield self.read(self.csrs['usb_out_ev_pending'])
            if out_ev != 1:
                raise TestFailure("out_ev should be 1 at the end of the test, was: {:02x}".format(out_ev))
            yield self.write(self.csrs['usb_out_ev_pending'], out_ev)

        # Status stage
        self.dut._log.info("status stage")

        in_ev = yield self.read(self.csrs['usb_in_ev_pending'])
        if in_ev != 0:
            raise TestFailure("in_ev should be 0 at the start of the test, was: {:02x}".format(in_ev))
        yield self.transaction_status_in(addr, epaddr_in)
        yield RisingEdge(self.dut.clk12)
        in_ev = yield self.read(self.csrs['usb_in_ev_pending'])
        if in_ev != 1:
            raise TestFailure("in_ev should be 1 at the end of the test, was: {:02x}".format(in_ev))
        yield self.write(self.csrs['usb_in_ev_pending'], in_ev)

    @cocotb.coroutine
    def control_transfer_in(self, addr, setup_data, descriptor_data=None):
        epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)
        epaddr_in = EndpointType.epaddr(0, EndpointType.IN)

        if (setup_data[0] & 0x80) == 0x00:
            raise Exception("setup_data indicated an OUT transfer, but you requested an IN transfer")

        setup_ev = yield self.read(self.csrs['usb_setup_ev_pending'])
        if setup_ev != 0:
            raise TestFailure("setup_ev should be 0 at the start of the test, was: {:02x}".format(setup_ev))

        # Setup stage
        self.dut._log.info("setup stage")
        yield self.transaction_setup(addr, setup_data)

        setup_ev = yield self.read(self.csrs['usb_setup_ev_pending'])
        if setup_ev != 1:
            raise TestFailure("setup_ev should be 1, was: {:02x}".format(setup_ev))
        yield self.write(self.csrs['usb_setup_ev_pending'], setup_ev)

        # Data stage
        in_ev = yield self.read(self.csrs['usb_in_ev_pending'])
        if in_ev != 0:
            raise TestFailure("in_ev should be 0 at the start of the test, was: {:02x}".format(in_ev))
        if (setup_data[7] != 0 or setup_data[6] != 0) and descriptor_data is None:
            raise Exception("setup_data indicates data, but no descriptor data was specified")
        if (setup_data[7] == 0 and setup_data[6] == 0) and descriptor_data is not None:
            raise Exception("setup_data indicates no data, but descriptor data was specified")
        if descriptor_data is not None:
            self.dut._log.info("data stage")
            yield self.transaction_data_in(addr, epaddr_in, descriptor_data)

        # Give the signal one clock cycle to perccolate through the event manager
        yield RisingEdge(self.dut.clk12)
        in_ev = yield self.read(self.csrs['usb_in_ev_pending'])
        if in_ev != 1:
            raise TestFailure("in_ev should be 1 at the end of the test, was: {:02x}".format(in_ev))
        yield self.write(self.csrs['usb_in_ev_pending'], in_ev)

        # Status stage
        self.dut._log.info("status stage")
        out_ev = yield self.read(self.csrs['usb_out_ev_pending'])
        if out_ev != 0:
            raise TestFailure("out_ev should be 0 at the start of the test, was: {:02x}".format(out_ev))
        yield self.transaction_status_out(addr, epaddr_out)
        yield RisingEdge(self.dut.clk12)
        out_ev = yield self.read(self.csrs['usb_out_ev_pending'])
        if out_ev != 1:
            raise TestFailure("out_ev should be 1 at the end of the test, was: {:02x}".format(out_ev))
        yield self.write(self.csrs['usb_out_ev_pending'], out_ev)

    @cocotb.coroutine
    def set_device_address(self, address):
        yield super().set_device_address(address)
        yield self.write(self.csrs['usb_address'], address)

