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
            self.adr = adr

        @cocotb.coroutine
        def write(self, value):
            yield self.wb.write(self.adr, value)

        @cocotb.coroutine
        def read(self):
            value = yield self.wb.read(self.adr)
            raise ReturnValue(value)

    def __init__(self, csrs, wishbone):
        self.wb = wishbone
        self.csrs = csrs

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
    def reset(self):
        self.dut.reset = 1
        yield ClockCycles(self.dut.clk, 10, rising=True)
        self.dut.reset = 0
        yield ClockCycles(self.dut.clk, 10, rising=True)


        yield ClockCycles(self.dut.clk, 10000, rising=True)

        val = yield self.csrs.cpucs.read()
        print(f'val = 0x{val:02x}')
        for i in range(10):
            yield self.csrs.cpucs.write(i)
            val = yield self.csrs.cpucs.read()
            print(f'val = 0x{val:02x}')
