from collections import namedtuple

import cocotb
from cocotb.monitors import BusMonitor
from cocotb.triggers import RisingEdge, FallingEdge


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
        self.wb_dat_w = self.dut.wishbone_cpu_dat_w
        self.wb_we = self.dut.wishbone_cpu_we
        self.wb_cyc = self.dut.wishbone_cpu_cyc
        self.wb_stb = self.dut.wishbone_cpu_stb
        self.wb_ack = self.dut.wishbone_cpu_ack

        self.address_override = None

    @cocotb.coroutine
    def _monitor_recv(self):
        # wait until there are no undefined signal values
        yield FallingEdge(self.dut.reset)

        while True:
            # wait for positive edge on ack to speed up compared to checking on each clock edge
            yield RisingEdge(self.wb_ack)

            if self.wb_cyc == 1 and self.wb_stb == 1 and self.wb_ack == 1:
                adr, dat_r, dat_w, we = map(int, (self.wb_adr, self.wb_dat_r, self.wb_dat_w, self.wb_we))
                if self.is_monitored_address(adr):
                    self._recv(self.RegisterAccess(adr, dat_r, dat_w, we))

    def is_monitored_address(self, adr):
        address_ranges = self.address_ranges if self.address_override is None else self.address_override
        for adr_min, adr_max in address_ranges:
            if adr_min <= adr <= adr_max:
                return True
        return False
