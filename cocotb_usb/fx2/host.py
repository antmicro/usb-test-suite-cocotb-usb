import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles, NullTrigger
from cocotb.result import TestFailure
from cocotb.utils import get_sim_time

from cocotb_usb.usb.pid import PID
from cocotb_usb.usb.packet import (wrap_packet, token_packet, data_packet,
                                   sof_packet, handshake_packet)
from cocotb_usb.usb.pp_packet import pp_packet

from cocotb_usb.wishbone import WishboneMaster
from cocotb_usb.host import UsbTest
from cocotb_usb.utils import parse_csr, assertEqual

from .usb_decoder import decode_packet

from .utils import _dbg
from .usb import FX2USB


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
        self.fx2_usb = FX2USB(self.dut.dut, parse_csr(csr_file))

    @cocotb.coroutine
    def wait_cpu(self, clocks):
        yield ClockCycles(self.dut.dut.oc8051_top.wb_clk_i, clocks, rising=True)

    @cocotb.coroutine
    def wait(self, time, units="us"):
        yield super().wait(time // 10, units=units)

    @cocotb.coroutine
    def reset(self):
        self.address = 0
        self.dut.reset = 1
        yield ClockCycles(self.dut.clk48_host, 10, rising=True)
        self.dut.reset = 0
        yield ClockCycles(self.dut.clk48_host, 10, rising=True)

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
        _dbg('>> %s' % decode_packet(packet))
        yield self.fx2_usb.receive_host_packet(packet)

    # Device->Host
    @cocotb.coroutine
    def host_expect_packet(self, packet, msg=None):
        _dbg('<? %s' % decode_packet(packet))
        result = yield self.fx2_usb.expect_device_packet(timeout=1e9) # 1ms max

        if result is None:
            current = get_sim_time("us")
            raise TestFailure(f"No full packet received @{current}")

        yield RisingEdge(self.dut.clk48_host)

        # Check the packet received matches
        expected = pp_packet(wrap_packet(packet))
        actual = pp_packet(wrap_packet(result))
        nak = pp_packet(wrap_packet(handshake_packet(PID.NAK)))
        _dbg('<< %s' % decode_packet(result))
        if (actual == nak) and (expected != nak):
            self.dut._log.warn("Got NAK, retry")
            yield Timer(self.RETRY_INTERVAL, 'us')
            return
        else:
            self.retry = False
            assertEqual(expected, actual, msg)
