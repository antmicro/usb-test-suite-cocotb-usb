import enum
from collections import namedtuple

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles, NullTrigger
from cocotb.result import ReturnValue
from cocotb.monitors import BusMonitor
from cocotb.utils import get_sim_time

from cocotb_usb.usb.pid import PID
from cocotb_usb.usb.packet import (wrap_packet, token_packet, data_packet,
                                   sof_packet, handshake_packet)
from cocotb_usb.usb.pp_packet import pp_packet

from cocotb_usb.wishbone import WishboneMaster
from cocotb_usb.host import UsbTest
from cocotb_usb.utils import parse_csr, assertEqual
from cocotb_usb import usb

from cocotb_usb.usb_decoder import decode_packet


class CSRs:
    class WishboneProxy:
        def __init__(self, wb, adr):
            self.wb = wb
            # work around WishboneMaster performing bit shift required by Litex
            # FX2 wishbone uses full addresses as it can address any byte
            self.adr = adr << 2

        @cocotb.coroutine
        def write(self, value):
            print('CSR WRITE: 0x%02x @0x%04x' % (self.adr >> 2, value))
            yield self.wb.write(self.adr, value)

        @cocotb.coroutine
        def read(self):
            value = yield self.wb.read(self.adr)
            print('CSR READ: 0x%02x @0x%04x' % (value, self.adr >> 2))
            raise ReturnValue(value)

    def __init__(self, csrs, wb):
        self.csrs = csrs
        self.wb = wb

    def __getattr__(self, name):
        adr = self.__dict__['csrs'][name]
        wb = self.__dict__['wb']
        return self.WishboneProxy(wb, adr)


class RegisterAccessMonitor(BusMonitor):
    """
    Monitors wishbone bus for access to registers in given address ranges.

    Args:
        address_ranges: list of tuples (address_min, address_max), inclusive
    """

    RegisterAccess = namedtuple('RegisterAccess', ['adr', 'dat_r', 'dat_w', 'we'])

    def __init__(self, dut, address_ranges, *args, **kwargs):
        self.address_ranges = address_ranges
        self.dut = dut
        super().__init__(*[dut, *args], **kwargs)

        self.wb_adr = self.dut.wishbone_cpu_adr
        self.wb_dat_r = self.dut.wishbone_cpu_dat_r
        self.wb_dat_w = self.dut.wishbone_cpu_dat_r
        self.wb_we = self.dut.wishbone_cpu_we
        self.wb_cyc = self.dut.wishbone_cpu_cyc
        self.wb_stb = self.dut.wishbone_cpu_stb
        self.wb_ack = self.dut.wishbone_cpu_ack

    @cocotb.coroutine
    def _monitor_recv(self):
        yield FallingEdge(self.dut.reset)

        while True:
            yield RisingEdge(self.clock)

            if self.wb_cyc == 1 and self.wb_stb == 1 and self.wb_ack == 1:
                adr, dat_r, dat_w, we = map(int, (self.wb_adr, self.wb_dat_r, self.wb_dat_w, self.wb_we))
                if self.is_monitored_address(adr):
                    self._recv(self.RegisterAccess(adr, dat_r, dat_w, we))

    def is_monitored_address(self, adr):
        for adr_min, adr_max in self.address_ranges:
            if adr_min <= adr <= adr_max:
                return True
        return False


class FX2USB:
    # implements FX2 USB peripheral outside of the simulation
    # TODO: CRC checks

    class IRQ(enum.IntEnum):
        SUDAV = 1
        SOF = 2
        SUTOK = 3

    class TState(enum.Enum):
        # each transaction (except isosynchronous transfers) has 3 steps,
        # first one is always sent by host
        # read the values as "waiting for X", so TOKEN can be interpreted as idle state
        TOKEN = 1
        DATA = 2
        HANDSHAKE = 3

    #  class TDir(enum.Enum):
    #      OUT = 1  # host -> dev
    #      IN = 2   # dev -> host

    def __init__(self, reg_monitor, fx2_csrs, wb_dbus):
        self.monitor = reg_monitor
        self.csrs = fx2_csrs
        self.dbus = wb_dbus

        self.monitor.add_callback(self.monitor_handler)
        self.reset_state()

    def reset_state(self):
        # host always starts transactions
        self.tstate = self.TState.TOKEN
        # store previous packets of a transaction between invocations
        self.token_packet = None
        self.data_packet = None

    @cocotb.coroutine
    def monitor_handler(self, reg_access):
        print('USB access:', reg_access)
        yield ClockCycles(self.dbus.clk, 0)

    @cocotb.coroutine
    def handle_token(self, p):
        # TODO: handle addr/endp token fields
        # it always comes from host
        if p.pid == PID.SETUP:
            self.token_packet = p
            # interrupt generated after successful SETUP packet
            yield self.assert_interrupt(self.IRQ.SUTOK)
            # clear busy and stall bits, TODO: do this without writing data bus? or at least hold cpu clock?
            ep0cs = yield self.csrs.ep0cs.read()
            yield self.csrs.ep0cs.write(ep0cs & (~0b11))
        else:
            self.reset_state()

    @cocotb.coroutine
    def handle_data(self, p):
        assert self.token_packet
        yield NullTrigger()

        tp = self.token_packet
        if tp.pid == PID.SETUP and tp.endp == 0:
            self.data_packet = p
            # copy data to SETUPDAT
            for i, b in enumerate(p.data):
                yield getattr(self.csrs, "setupdat%d" % i).write(b)
            yield self.assert_interrupt(self.IRQ.SUDAV)
            # now firmware should ack/stall EP0 (EP0CS)

    @cocotb.coroutine
    def handle_handshake(self, p):
        assert self.token_packet
        assert self.data_packet
        yield NullTrigger()

    @cocotb.coroutine
    def handle_sof(self, p):
        # update USBFRAMEH:L (FIXME: should also be incremented on missing/garbled frames, see docs)
        frameh, framel = ((p.framenum & 0xff00) >> 8), (p.framenum & 0xff)
        print('time us: ', get_sim_time('us'))
        yield self.csrs.usbframeh.write(frameh)
        yield self.csrs.usbframel.write(framel)
        # generate interrupt
        yield self.assert_interrupt(self.IRQ.SOF)


    @cocotb.coroutine
    def receive_host_packet(self, packet):
        p = decode_packet(packet)
        print('p =', end=' '); __import__('pprint').pprint(p)

        # check packet category and decide wheather it is correct for the current state
        if p.category == 'TOKEN':
            # handle SOF as it is only the token
            if p.pid == PID.SOF:
                yield self.handle_sof(p)
                return

            if self.tstate != self.TState.TOKEN:
                raise Exception('received %s token in state %s' % (p.pid, self.tstate))

            yield self.handle_token(p)
            print('State: %s -> %s' % (self.tstate, self.TState.DATA))
            self.tstate = self.TState.DATA

        elif p.category == 'DATA':
            if self.tstate != self.TState.DATA:
                raise Exception('received %s token in state %s' % (p.pid, self.tstate))

            yield self.handle_data(p)
            print('State: %s -> %s' % (self.tstate, self.TState.HANDSHAKE))
            self.tstate = self.TState.HANDSHAKE

        elif p.category == 'HANDSHAKE':
            if self.tstate != self.TState.HANDSHAKE:
                raise Exception('received %s token in state %s' % (p.pid, self.tstate))

            yield self.handle_handshake(p)
            print('State: %s -> %s' % (self.tstate, self.TState.TOKEN))
            self.reset_state()
        else:
            raise NotImplementedError('Received unhandled %s token in state %s' % (p.pid, self.tstate))


    @cocotb.coroutine
    def expect_device_packet(self, timeout):
        yield NullTrigger()
        raise ReturnValue(handshake_packet(PID.NAK))
        #  raise ReturnValue(handshake_packet(PID.STALL))

    @cocotb.coroutine
    def assert_interrupt(self, irq):
        print('FX2 interrupt: ', irq)
        usbirq = yield self.csrs.usbirq.read()
        if irq == self.IRQ.SUDAV:
            yield self.csrs.usbirq.write(usbirq | (1 << 0))
        elif irq == self.IRQ.SOF:
            yield self.csrs.usbirq.write(usbirq | (1 << 1))
        elif irq == self.IRQ.SUTOK:
            yield self.csrs.usbirq.write(usbirq | (1 << 2))


class UsbTestFX2(UsbTest):
    """
    Host implementation for FX2 USB tests.
    It is used for testing higher level USB logic of FX2 firmware,
    instead of testing the USB peripheral. Wishbone data bus is used
    to intercept USB communication at register level.
    """
    def __init__(self, dut, csr_file, **kwargs):
        self.dut = dut

        self.clock_period = 20830  # ps, ~48MHz
        cocotb.fork(Clock(dut.clk, self.clock_period, 'ps').start())

        self.wb = WishboneMaster(dut, "wishbone", dut.clk, timeout=20)
        self.csrs = CSRs(parse_csr(csr_file), self.wb)

        usb_adr_ranges = [
            (0xe500, 0xe6ff),
            (0xe740, 0xe7ff),
            (0xf000, 0xffff),
        ]
        self.fx2_monitor = RegisterAccessMonitor(self.dut, usb_adr_ranges,
                                                 name='wishbone', clock=dut.dut.sys_clk,
                                                 callback=lambda rec: print('Rec: ', rec))
        self.fx2_usb = FX2USB(self.fx2_monitor, self.csrs, self.wb)

    @cocotb.coroutine
    def wait_cpu(self, clocks):
        yield ClockCycles(self.dut.dut.oc8051_top.wb_clk_i, clocks, rising=True)

    #  @cocotb.coroutine
    #  def wait(self, time, units="us"):
    #      yield NullTrigger()

    @cocotb.coroutine
    def reset(self):
        self.address = 0
        self.dut.reset = 1
        yield ClockCycles(self.dut.clk, 10, rising=True)
        self.dut.reset = 0
        yield ClockCycles(self.dut.clk, 10, rising=True)

    @cocotb.coroutine
    def port_reset(self, time=10e3, recover=False):
        yield NullTrigger()

        self.dut._log.info("[Resetting port for {} us]".format(time))

        #  yield self.wait(time, "us")
        yield self.wait(1, "us")
        self.connect()
        if recover:
            #  yield self.wait(1e4, "us")
            yield self.wait(1, "us")

    @cocotb.coroutine
    def connect(self):
        yield NullTrigger()

    @cocotb.coroutine
    def disconnect(self):
        """Simulate device disconnect, both lines pulled low."""
        yield NullTrigger()
        self.address = 0

    # Host->Device
    @cocotb.coroutine
    def _host_send_packet(self, packet):
        yield self.fx2_usb.receive_host_packet(packet)

    # Device->Host
    @cocotb.coroutine
    def host_expect_packet(self, packet, msg=None):
        result = yield self.fx2_usb.expect_device_packet(timeout=1e9) # 1ms max

        if result is None:
            current = get_sim_time("us")
            raise TestFailure(f"No full packet received @{current}")

        # Check the packet received matches
        expected = pp_packet(wrap_packet(packet))
        actual = pp_packet(wrap_packet(result))
        nak = pp_packet(wrap_packet(handshake_packet(PID.NAK)))
        if (actual == nak) and (expected != nak):
            self.dut._log.warn("Got NAK, retry")
            yield Timer(self.RETRY_INTERVAL, 'us')
            return
        else:
            self.retry = False
            assertEqual(expected, actual, msg)
