import enum
from collections import namedtuple
from functools import reduce

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles, NullTrigger
from cocotb.result import ReturnValue, TestFailure
from cocotb.monitors import BusMonitor
from cocotb.utils import get_sim_time

from cocotb_usb.usb.pid import PID
from cocotb_usb.usb.packet import (wrap_packet, token_packet, data_packet,
                                   sof_packet, handshake_packet)
from cocotb_usb.usb.pp_packet import pp_packet

from cocotb_usb.wishbone import WishboneMaster
from cocotb_usb.host import UsbTest
from cocotb_usb.utils import parse_csr,assertEqual
from cocotb_usb import usb

from cocotb_usb.usb_decoder import decode_packet


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

def bit(n):
    return 1 << n

def testbit(val, n):
    return (val & bit(n)) != 0

def msb(word):
    return (0xff00 & word) >> 8

def lsb(word):
    return 0xff & word

def word(msb, lsb):
    return ((msb & 0xff) << 8) | (lsb & 0xff)


def bitupdate(reg, *, set=None, clear=None, clearbits=None, setbits=None):
    """
    Convenience function for bit manipulations.

    reg:       original value
    set:       bitmask of values to be set
    clear:     bitmask of values to be cleared
    setbits:   list of bit offsets to use for constructing `set` mask (`set` must be None)
    clearbits: list of bit offsets to use for constructing `clear` mask (`clear` must be None)
    """
    # convert bit lists to masks
    bitsmask = lambda bits: reduce(lambda p, q: p | q, ((1 << b) for b in bits))
    if clearbits:
        assert clear is None, "'clear' must not be used when using 'clearbits'"
        clear = bitsmask(clearbits)
    if setbits:
        assert set is None, "'set' must not be used when using 'setbits'"
        set = bitsmask(setbits)
    # set default values, assert when nothing happens (we don't use this function if need no change)
    assert set is not None or clear is not None, 'Nothing to set/clear'
    set = 0 if set is None else set
    clear = 0 if clear is None else clear
    # clear and set mask overlap
    assert (set & clear) == 0, 'Bit masks overlap: set(%s) clear(%s)' % (bin(set), bin(clear))
    # perform bit operation
    reg = (int(reg) & (~clear)) | set
    return reg


class FX2USB:
    # implements FX2 USB peripheral outside of the simulation
    # TODO: CRC checks

    class IRQ(enum.IntEnum):
        SUDAV = 0
        SOF = 1
        SUTOK = 2
        SUSP = 3
        URES = 4
        HSGRANT = 5
        EP01ACK = 6

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

    def __init__(self, dut, csrs):
        """
        dut: the actual dut from dut.v (not tb.v)
        """
        self.dut = dut
        self.csrs = csrs

        usb_adr_ranges = [
            (0xe500, 0xe6ff),
            (0xe740, 0xe7ff),
            (0xf000, 0xffff),
        ]
        self.monitor = RegisterAccessMonitor(self.dut, usb_adr_ranges,
                                             name='wishbone', clock=dut.sys_clk,
                                             callback=self.monitor_handler)
        self.reset_state()

        self.armed_ep_lengths = {i: None for i in [0, 1, 2, 4, 6, 8]}

    def reset_state(self):
        # host always starts transactions, state means what we should receive next
        self.tstate = self.TState.TOKEN
        # store previous packets of a transaction between invocations
        self.token_packet = None
        self.data_packet = None

    def monitor_handler(self, wb):
        # clear interrupt flags on writes instead of setting register value
        clear_on_write_regs = ['ibnirq', 'nakirq', 'usbirq', 'epirp', 'gpifirq',
                               *('ep%dfifoirq' % i for i in [2, 4, 6, 8])]
        for reg in clear_on_write_regs:
            if reg in self.csrs.keys():  # only implemented registers
                if wb.adr == self.csrs[reg] and wb.we:
                    # use the value that shows up on read signal as last register value
                    last_val = wb.dat_r
                    # we can set the new value now, as at this moment value from wishbone bus
                    # has already been written
                    self.set_csr(reg, bitupdate(last_val, clear=wb.dat_w))

        # endpoint arming
        ep_len = lambda prefix: word(self.get_csr(prefix + 'h'), self.get_csr(prefix + 'l'))
        if wb.adr == self.csrs['ep0bcl']:
            sdpauto = (self.get_csr('sudptrctl') & 0b1) != 0
            if sdpauto:  # should get length from descriptors
                raise NotImplementedError()
            else:
                self.armed_ep_lengths[0] = ep_len('ep0bc')
                # TODO: what when EP has already been armed?
            # set BUSY bit in EP0CS
            self.update_csr('ep0cs', setbits=[1])

        #  for reg in []

        #  if wb.we:
        #      csrs = filter(lambda kv: kv[1] == wb.adr, self.csrs.items())
        #      print('WRITE: 0x%02x @0x%04x: %s' % (wb.dat_w, wb.adr, ', '.join(kv[0] for kv in csrs)))

    # handle the date in TOKEN packet
    # return True if it has been handled
    # set appropriate next state (what we will receive next - DATA/HANDSHAKE)
    # when returned False, state will be reset, else the token packet will be stored
    def handle_token(self, p):
        # TODO: handle addr/endp token fields
        # it always comes from host

        if p.pid == PID.SOF:
            # update USBFRAMEH:L (FIXME: should also be incremented on missing/garbled frames, see docs)
            self.set_csr('usbframeh', msb(p.framenum))
            self.set_csr('usbframel', lsb(p.framenum))
            # generate interrupt
            self.assert_interrupt(self.IRQ.SOF)
            return False  # no data/handshake, just reset state

        elif p.pid == PID.SETUP:
            # interrupt generated after successful SETUP packet
            self.assert_interrupt(self.IRQ.SUTOK)
            # update ep status
            self.update_csr('ep0cs', setbits=[7], clearbits=[1, 0])
            self.tstate = self.TState.DATA
            return True

        # OUT are handled in data stage
        elif p.pid == PID.OUT:
            self.tstate = self.TState.DATA
            return True

        # in trasnfers are handled now, as testbench will next call expect_device_packet()
        # then host will send ACK, so next state is handshake
        elif p.pid == PID.IN:
            return self.handle_data_in(p)

        return False

    def handle_data_in(self, tp):

        if tp.endp == 0:
            hsnak = testbit(self.get_csr('ep0cs'), 7)
            stall = testbit(self.get_csr('ep0cs'), 0)
            print('hsnak', end=' '); __import__('pprint').pprint(hsnak)
            print('stall', end=' '); __import__('pprint').pprint(stall)
            # as long as HSNAK has not been cleared, we nak all transfers
            # we also NAK if endpoint has not been armed
            if hsnak:
                self.to_send = handshake_packet(PID.NAK)
            elif stall:
                self.to_send = handshake_packet(PID.STALL)
            else:
                # IN can mean STATUS stage on EP0, so send empty packet
                if self.armed_ep_lengths[0] is None:
                    self.to_send = data_packet(PID.DATA0, [])
                else:
                    assert False, 'payload from ep0!'
                    payload = list(range(self.armed_ep_lengths[0]))
                    self.to_send = data_packet(PID.DATA0, payload)
            return True
        else:
            assert False

        #  # if endpoint is not armed, do what EPxCS specifies
        #  if self.armed_ep_lengths[tp.endp] is None:
        #      if tp.endp == 0:
        #          hsnak = testbit(self.get_csr('ep0cs'), 7)
        #          stall = testbit(self.get_csr('ep0cs'), 0)
        #          # as long as HSNAK has not been cleared, we nak all transfers
        #          if hsnak:
        #              self.to_send = handshake_packet(PID.NAK)
        #          elif stall:
        #          return False
        #      else:
        #          assert False
        #  # if endpoint has been armed get the endpoint data and send it back to host
        #  # TODO: endpoint data buffering
        #  else:
        #      l = self.armed_ep_lengths[tp.endp]
        #      self.armed_ep_lengths[tp.endp] = None
        #
        #      if tp.endp == 0:
        #          ep0buf = 0x740
        #          payload = list(range(l))  # FIXME: fake data
        #      else:
        #          __import__('ipdb').set_trace()
        #      self.to_send = data_packet(PID.DATA0, payload)
        #      self.tstate = self.TState.HANDSHAKE
        #      return True

    # handle DATA/HANDSHAKE reception
    def handle_other(self, p):
        assert self.token_packet
        tp = self.token_packet

        # different action depending on token pid
        if tp.pid == PID.SETUP:
            if p.pid == PID.DATA0 and tp.endp == 0:
                self.data_packet = p
                # copy data to SETUPDAT
                for i, b in enumerate(p.data):
                    self.set_csr('setupdat%d' % i, b)
                self.assert_interrupt(self.IRQ.SUDAV)
                # send acknowledge
                self.to_send = handshake_packet(PID.ACK)
                return True
            else:
                __import__('ipdb').set_trace()

        # we got OUT token, now we receive data from host
        elif tp.pid == PID.OUT:
            assert False

        elif tp.pid == PID.IN:
            assert False
            assert False

        else:
            __import__('ipdb').set_trace()

        # on any other token something went wrong
        __import__('ipdb').set_trace()
        return False

    @cocotb.coroutine
    def receive_host_packet(self, packet):
        # this is called when host sends data, we should set self.send_to in this method
        p = decode_packet(packet)
        print('p =', end=' '); __import__('pprint').pprint(p)

        yield ClockCycles(self.dut.sys_clk, len(packet))

        # reset state if host sends wrong packet category (should not happen)
        if self.tstate.name != p.category:
            self.reset_state()
        elif self.tstate == self.TState.TOKEN:
            if self.handle_token(p):
                self.token_packet = p
            else:
                self.reset_state()
        else:
            self.handle_other(p)
            self.reset_state()

        yield ClockCycles(self.dut.sys_clk, 1)

    @cocotb.coroutine
    def expect_device_packet(self, timeout):
        #  #  if self.tstate == self.TState.HANDSHAKE:
        #  self.monitor.address_override = [(0xe6a0, 0xe6a0)] # ep0cs
        #  reg = yield self.monitor.wait_for_recv(timeout)
        yield NullTrigger()
        to_send = self.to_send
        self.to_send = None
        return to_send

    def update_csr(self, name, *args, immediate=False, **kwargs):
        val = getattr(self.dut, 'fx2csr_' + name)
        if immediate:
            getattr(self.dut, 'fx2csr_' + name).setimmediatevalue(bitupdate(val, *args, **kwargs))
        else:
            setattr(self.dut, 'fx2csr_' + name, bitupdate(val, *args, **kwargs))

    def set_csr(self, name, value, immediate=False):
        if immediate:
            getattr(self.dut, 'fx2csr_' + name).setimmediatevalue(value)
        else:
            setattr(self.dut, 'fx2csr_' + name, value)

    def get_csr(self, name):
        return int(getattr(self.dut, 'fx2csr_' + name))



    def assert_interrupt(self, irq):
        print('FX2 interrupt: ', irq)
        if irq in self.IRQ and 0 <= irq <= 6:
            self.update_csr('usbirq', setbits=[irq])
        else:
            raise NotImplementedError('Unexpected IRQ: %s' % irq)


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
