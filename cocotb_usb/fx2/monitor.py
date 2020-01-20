import enum
from collections import namedtuple

import cocotb
from cocotb.monitors import BusMonitor
from cocotb.triggers import RisingEdge, FallingEdge


class ExternalRAMMonitor(BusMonitor):
    """
    Monitors XRAM wishbone bus for reads/writes.

    Args:
        adr_spec: list of monitored addresses or tuples of
                  (min_adr, max_adr), inclusive

    """

    Access = namedtuple('Access', ['adr', 'dat_r', 'dat_w', 'we', 'ack'])

    def __init__(self, dut, adr_spec, *args, **kwargs):
        self.dut = dut
        kwargs['clock'] = self.dut.clk
        super().__init__(*[dut, *args], **kwargs)

        # convert all the single addresses to tuples
        self.adr_spec = [a if isinstance(a, tuple) else (a, a) for a in adr_spec]

        self.wb_adr = self.dut.wishbone_cpu_adr
        self.wb_dat_r = self.dut.wishbone_cpu_dat_r
        self.wb_dat_w = self.dut.wishbone_cpu_dat_w
        self.wb_we = self.dut.wishbone_cpu_we
        self.wb_cyc = self.dut.wishbone_cpu_cyc
        self.wb_stb = self.dut.wishbone_cpu_stb
        self.wb_ack = self.dut.wishbone_cpu_ack

    @cocotb.coroutine
    def _monitor_recv(self):
        # wait until there are no undefined signal values
        yield FallingEdge(self.dut.reset)

        while True:
            yield RisingEdge(self.dut.sys_clk)

            # send even without ack, so that handler can do something when read is issued, before an ack
            if self.wb_cyc == 1 and self.wb_stb == 1:
                adr, dat_r, dat_w, we, ack = \
                    map(int, (self.wb_adr, self.wb_dat_r, self.wb_dat_w, self.wb_we, self.wb_ack))
                if self.is_in_spec(adr):
                    self._recv(self.Access(adr, dat_r, dat_w, we, ack))

    def is_in_spec(self, adr):
        for min_adr, max_adr in self.adr_spec:
            if min_adr <= adr <= max_adr:
                return True
        return False


# new SFRs introduced (or modified) in FX2
FX2_SFRS = {
    'IOA':            0x80,
    'DPL1':           0x84,
    'DPH1':           0x85,
    'DPS':            0x86,
    'CKCON':          0x8e,

    'IOB':            0x90,
    'EXIF':           0x91,
    'MPAGE':          0x92,
    'AUTOPTRH1':      0x9a,
    'AUTOPTRL1':      0x9b,
    'AUTOPTRH2':      0x9d,
    'AUTOPTRL2':      0x9e,

    'IOC':            0xa0,
    'INT2CLR':        0xa1,
    'INT4CLR':        0xa2,
    'IE':             0xa8,
    'EP2468STAT':     0xaa,
    'EP24FIFOFLAGS':  0xab,
    'EP68FIFOFLAGS':  0xac,
    'AUTOPTRSETUP':   0xaf,

    'IOD':            0xb0,
    'IOE':            0xb1,
    'OEA':            0xb2,
    'OEB':            0xb3,
    'OEC':            0xb4,
    'OED':            0xb5,
    'OEE':            0xb6,
    'IP':             0xb8,
    'EP01STAT':       0xba,
    'GPIFTRIG':       0xbb,
    'GPIFSGLDATH':    0xbd,
    'GPIFSGLDATLX':   0xbe,
    'GPIFSGLDATLNOX': 0xbf,

    'SCON1':          0xc0,
    'SBUF1':          0xc1,
    'T2CON':          0xc8,
    'RCAP2L':         0xca,
    'RCAP2H':         0xcb,
    'TL2':            0xcc,
    'TH2':            0xcd,

    'EICON':          0xd8,
    'EIE':            0xe8,
    'EIP':            0xf8,
}
# create the reverse mapping (types are different so there will be no conflicts)
FX2_SFRS.update({adr: name for name, adr in FX2_SFRS.items()})


class SFRMonitor(BusMonitor):
    """
    Monitors internal RAM writes/reads to FX2 SFRs.
    SFRs are located at IRAM locations 0x80-0xff, but are accessed only using
    'direct' addressing mode.
    """

    Access = namedtuple('Access', ['adr', 'data', 'sfr', 'is_write'])

    def __init__(self, dut, *args, **kwargs):
        self.dut = dut
        kwargs['clock'] = self.dut.sys_clk
        super().__init__(*[dut, *args], **kwargs)

    @cocotb.coroutine
    def _monitor_recv(self):
        # wait until there are no undefined signal values
        yield FallingEdge(self.dut.reset)

        # get signals from the 8051 model
        top = self.dut.oc8051_top
        decoder = top.oc8051_decoder1
        mem = top.oc8051_memory_interface1
        sfr = top.oc8051_sfr1

        # addressing constants from oc8051_defines.v
        rd_addressing = {
            'RRS_RN':   0b000,  # registers
            'RRS_I':    0b001,  # indirect addressing (op2)
            'RRS_D':    0b010,  # direct addressing
            'RRS_SP':   0b011,  # stack pointer
            'RRS_B':    0b100,  # b register
            'RRS_DPTR': 0b101,  # data pointer
            'RRS_PSW':  0b110,  # program status word
            'RRS_ACC':  0b111,  # acc
        }
        wr_addressing = {
            'RWS_RN': 0b000,  # registers
            'RWS_D':  0b001,  # direct addressing
            'RWS_I':  0b010,  # indirect addressing
            'RWS_SP': 0b011,  # stack pointer
            'RWS_D3': 0b101,  # direct address (op3)
            'RWS_D1': 0b110,  # direct address (op1)
            'RWS_B':  0b111,  # b register
        }
        rd_sel_direct = [rd_addressing['RRS_D']]
        wr_sel_direct = [wr_addressing[i] for i in ['RWS_D', 'RWS_D1', 'RWS_D3']]

        is_sfr_adr = lambda adr: 0x80 <= adr <= 0xff

        while True:
            yield RisingEdge(top.wb_clk_i)

            # pass objects to self.Access so that handler can modify them (for read)
            wr_sel = decoder.ram_wr_sel
            rd_sel = decoder.ram_rd_sel
            wr_addr = mem.wr_addr
            rd_addr = mem.rd_addr
            # it seems that dat1 is used as input and dat0 as output
            # for all SFRs, but that may not be always True

            had_wr_access = False
            had_rd_access = False

            if int(wr_sel) in wr_sel_direct and is_sfr_adr(int(wr_addr)):
                wr_data = sfr.dat1
                access = self.Access(adr=wr_addr, data=wr_data,
                                     sfr=FX2_SFRS.get(int(wr_addr), None),
                                     is_write=True)
                self._recv(access)
                had_wr_access = True

            if int(rd_sel) in rd_sel_direct and is_sfr_adr(int(rd_addr)):
                rd_data = sfr.dat0
                access = self.Access(adr=rd_addr, data=rd_data,
                                     sfr=FX2_SFRS.get(int(rd_addr), None),
                                     is_write=False)
                self._recv(access)
                had_rd_access = True
