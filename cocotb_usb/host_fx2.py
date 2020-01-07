from collections import namedtuple

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles
from cocotb.result import ReturnValue
from cocotb.monitors import BusMonitor

from cocotb_usb.wishbone import WishboneMaster
from cocotb_usb.host import UsbTest
from cocotb_usb.utils import parse_csr


class CSRs:
    class WishboneProxy:
        def __init__(self, wb, adr):
            self.wb = wb
            # work around WishboneMaster performing bit shift required by Litex
            # FX2 wishbone uses full addresses as it can address any byte
            self.adr = adr << 2

        @cocotb.coroutine
        def write(self, value):
            yield self.wb.write(self.adr, value)

        @cocotb.coroutine
        def read(self):
            value = yield self.wb.read(self.adr)
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
        self.monitor = RegisterAccessMonitor(self.dut, usb_adr_ranges,
                                             name='wishbone', clock=dut.dut.sys_clk,
                                             callback=lambda rec: print('Rec: ', rec))

    @cocotb.coroutine
    def wait_cpu(self, clocks):
        yield ClockCycles(self.dut.dut.oc8051_top.wb_clk_i, clocks, rising=True)

    @cocotb.coroutine
    def reset(self):
        self.dut.reset = 1
        yield ClockCycles(self.dut.clk, 10, rising=True)
        self.dut.reset = 0
        yield ClockCycles(self.dut.clk, 10, rising=True)

        yield self.wait_cpu(100)

        cpuspd_choices = [0b00, 0b01, 0b10]
        for i in range(3):
            for cpuspd in cpuspd_choices:
                cpucs = cpuspd << 3
                self.dut._log.info('Setting CPUSPD = %d (CPUCS = 0x%02x)' % (cpuspd, cpucs))
                yield self.csrs.cpucs.write(cpucs)

                yield self.wait_cpu(100)

                cpucs = yield self.csrs.cpucs.read()
                cpuspd = (cpucs >> 3) & 0b11
                self.dut._log.info('Read    CPUSPD = %d (CPUCS = 0x%02x)' % (cpuspd, cpucs))

                yield self.wait_cpu(100)

        import sys; sys.exit(0)
