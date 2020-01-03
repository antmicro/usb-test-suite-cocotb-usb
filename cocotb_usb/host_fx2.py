import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.result import ReturnValue

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
            __import__('pprint').pprint(f'write adr: 0x{self.adr:04x}')
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


class UsbTestFX2(UsbTest):
    """
    Host implementation for FX2 USB tests.
    It is used for testing higher level USB logic of FX2 firmware,
    instead of testing the USB peripheral. Wishbone data bus is used
    to intercept USB communication at register level.
    """
    def __init__(self, dut, csr_file, **kwargs):
        self.dut = dut
        #  super().__init__(dut, **kwargs)
        self.clock_period = 20830

        cocotb.fork(Clock(dut.clk, self.clock_period, 'ps').start())

        self.wb = WishboneMaster(dut, "wishbone", dut.clk, timeout=20)
        self.csrs = CSRs(parse_csr(csr_file), self.wb)

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
