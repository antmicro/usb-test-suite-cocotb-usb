import enum

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, ClockCycles, NullTrigger
from cocotb.result import ReturnValue, TestFailure
from cocotb.utils import get_sim_time

from cocotb_usb.usb.pid import PID
from cocotb_usb.usb.packet import (wrap_packet, token_packet, data_packet,
                                   sof_packet, handshake_packet)

from .usb_decoder import decode_packet
from .state_machine import StateMachine

from .utils import *
from .utils import _dbg, bit, testbit, msb, lsb, word, bitupdate
from .monitor import ExternalRAMMonitor, SFRMonitor, FX2_SFRS


def ep2toggle_index(ep, io=0):
    """Get index of data toggle bit for given endpoint and direction."""
    if ep == 0:
        return 0
    elif ep == 1:
        return 1 + io
    else:
        return ep // 2 + 2  # 3-6


# TODO: try using definitions from fx2-sim directly instead of copying code
_ram_areas = {  # TRM 5.6
    'main_ram':       (0x0000, 16 * 2**10),
    'scratch_ram':    (0xe000, 512),
    'gpif_waveforms': (0xe400, 128),
    'ezusb_csrs':     (0xe500, 512),
    'ep0inout':       (0xe740, 64),
    'ep1out':         (0xe780, 64),
    'ep1in':          (0xe7c0, 64),
    'ep2468':         (0xf000, 4 * 2**10),
}

def xram_mem_set(dut, adr, data):
    for mem, (origin, size) in _ram_areas.items():
        if origin <= adr <= origin + size:
            mem_name = 'mem_%s' % mem
            storage = getattr(dut, mem_name)
            storage[adr - origin].setimmediatevalue(data)
            return


def xram_mem_get(dut, adr):
    for mem, (origin, size) in _ram_areas.items():
        if origin <= adr <= origin + size:
            mem_name = 'mem_%s' % mem
            storage = getattr(dut, mem_name)
            return int(storage[adr - origin])
    raise KeyError('Address not in XRAM storage: 0x%04x' % adr)


def setupdat_bytes_to_csr(setupdat):
    # construct a SETUPDAT 64-bit value:
    # (!) litex generates names with revesed numbers:
    #   FX2 SETUPDAT[0] = setupdat7_w = fx2csr_setupdat[63:56]
    setupdat_masks = [b << (8 * i) for i, b in enumerate(reversed(setupdat))]
    setupdat64 = reduce(lambda acc, b: acc | b, setupdat_masks)
    return setupdat64


def setupdat_csr_to_bytes(setupdat64):
    setupdat_bytes = [((setupdat64 & (0xff << (8 * i))) >> (8 * i)) for i in range(8)]
    setupdat = list(reversed(setupdat_bytes))
    return setupdat


class Autopointers:
    def __init__(self, fx2usb):
        self.fx2usb = fx2usb
        # AUTOPTRSETUP
        self.aptr1inc = True
        self.aptr2inc = True
        self.aptren = False
        # addresses AUTOPTR[H/L]1, AUTOPTR[H/L]2
        self.autoptr1 = 0
        self.autoptr2 = 0

    def handle_sfr_access(self, access):
        if access.is_write:
            if access.adr == FX2_SFRS['AUTOPTRSETUP']:
                self.aptren = testbit(access.data, 0)
                self.aptr1inc = testbit(access.data, 1)
                self.aptr2inc = testbit(access.data, 2)
            elif access.adr == FX2_SFRS['AUTOPTRH1']:
                self.autoptr1 = word(access.data, lsb(self.autoptr1))
            elif access.adr == FX2_SFRS['AUTOPTRL1']:
                self.autoptr1 = word(msb(self.autoptr1), access.data)
            elif access.adr == FX2_SFRS['AUTOPTRH2']:
                self.autoptr2 = word(access.data, lsb(self.autoptr2))
            elif access.adr == FX2_SFRS['AUTOPTRL2']:
                self.autoptr2 = word(msb(self.autoptr2), access.data)
        else:
            if access.adr == FX2_SFRS['AUTOPTRSETUP']:
                access.data.setimmediatevalue(
                    int(self.aptren)   << 0 |
                    int(self.aptr1inc) << 1 |
                    int(self.aptr2inc) << 2)
            elif access.adr == FX2_SFRS['AUTOPTRH1']:
                access.data.setimmediatevalue(msb(self.autoptr1))
            elif access.adr == FX2_SFRS['AUTOPTRL1']:
                access.data.setimmediatevalue(lsb(self.autoptr1))
            elif access.adr == FX2_SFRS['AUTOPTRH2']:
                access.data.setimmediatevalue(msb(self.autoptr2))
            elif access.adr == FX2_SFRS['AUTOPTRL2']:
                access.data.setimmediatevalue(lsb(self.autoptr2))

    def handle_xram_access(self, access):
        # handle access to XAUTODAT1 and XAUTODAT2
        if access.adr == 0xe67b:  # XAUTODAT1
            if access.we == 0: # read (should be before ack!)
                # read value at memory location pointed by autopointer
                value = xram_mem_get(self.fx2usb.dut, self.autoptr1)
                # set value of xautodat1 so that in next cycle it will be read on bus
                self.fx2usb.set_csr('xautodat1', value, immediate=True)
                if access.ack:
                    self.autoptr1 += 1
            else: # write
                if access.ack:
                    xram_mem_set(self.fx2usb.dut, self.autoptr1, access.dat_w)
                    self.autoptr1 += 1
        elif access.adr == 0xe67c:  # XAUTODAT2
            if access.we == 0: # read (should be before ack!)
                value = xram_mem_get(self.fx2usb.dut, self.autoptr2)
                self.fx2usb.set_csr('xautodat2', value, immediate=True)
                if access.ack:
                    self.autoptr2 += 1
            else: # write
                if access.ack:
                    xram_mem_set(self.fx2usb.dut, self.autoptr2, access.dat_w)
                    self.autoptr2 += 1




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

    class ControlTransferType(enum.Enum):
        # control transfer can have data stage IN/OUT or no data stage
        # status stage has opposite direction to data stage or IN if there is no data stage
        STATUS_OUT = 1
        STATUS_IN = 2

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
        self.xram_monitor = ExternalRAMMonitor(self.dut, usb_adr_ranges,
                                               name='xram', callback=self.xram_access_handler)
        self.sfr_monitor = SFRMonitor(self.dut, name='sfr', callback=self.sfr_access_handler)
        self.autopointers = Autopointers(self)
        self.reset_state()
        self.ctrl_transfer = None

        self.armed_ep_lengths = {i: None for i in [0, 1, 2, 4, 6, 8]}

        # construct transaction state machine
        S = self.TransactionState
        self.transaction_state_machine = StateMachine(S.WAIT_TOKEN, {
            S.WAIT_TOKEN: self.on_wait_token,
            S.WAIT_DATA_OUT: self.on_wait_data,
            S.WAIT_HANDSHAKE_OUT: self.on_wait_handshake,
        })

    def send_to_host(self, packet):
        #  _dbg('send_to_host(%s)' % packet)
        self.expect_data_callback = lambda: packet

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
        _dbg('(IRQ):', irq)
        if irq in self.IRQ and 0 <= irq <= 6:
            self.update_csr('usbirq', setbits=[irq])
        else:
            raise NotImplementedError('Unexpected IRQ: %s' % irq)

    ### Transaction state machine ##############################################

    class TransactionState(enum.Enum):
        WAIT_TOKEN = 1
        # -> if OUT                        => WAIT_DATA_OUT
        #    if IN  -> send data IN        => WAIT_HANDSHAKE_OUT
        #    else                          => WAIT_TOKEN
        WAIT_DATA_OUT = 2
        # -> if data OUT -> send handshake => WAIT_TOKEN
        #    else                          => WAIT_TOKEN
        WAIT_HANDSHAKE_OUT = 3
        # -> if handshake
        #       -> if ACK                  => WAIT_TOKEN
        #          if NACK -> send data IN => WAIT_HANDSHAKE_OUT
        #    else                          => WAIT_TOKEN

    def reset_state(self):
        _dbg('reset_state')
        self.token_packet = None
        self.received_data_callback = None
        self.expect_data_callback = None
        self.ack_callback = None

    def handle_packet(self, p):
        # reset state if we receive something when in WAIT_TOKEN
        if self.transaction_state_machine.state == self.TransactionState.WAIT_TOKEN:
            self.reset_state()

        self.packet = p

        # first fix code that sets address
        #  # ignore packets with different address then ours
        #  if p.pid in [PID.SETUP, PID.OUT, PID.IN] and p.addr != self.get_csr('fnaddr'):
        #      _dbg('Ignoring packet with address 0x%02x (ours = 0x%02x)' % (p.addr, self.get_csr('fnaddr')))
        #      return

        last = self.transaction_state_machine.state
        new = self.transaction_state_machine.next()
        _dbg('[STATE_MACHINE] %s -> %s' % (last, new))

    def on_wait_token(self, s):
        p, S = self.packet, self.TransactionState
        self.token_packet = p

        if p.pid == PID.SOF:
            self.handle_sof()
            return S.WAIT_TOKEN
        elif p.pid == PID.SETUP or p.pid == PID.OUT:  # next direction OUT
            self.handle_token_out() # should assign self.received_data_callback
            return S.WAIT_DATA_OUT
        elif p.pid == PID.IN:
            # next state depends on success:
            # whether we NAK/STALLed or we sent data and wait for ACK
            if self.handle_token_in():
                return S.WAIT_HANDSHAKE_OUT
            else:
                return S.WAIT_TOKEN
        else:
            # error
            return S.WAIT_TOKEN

    def on_wait_data(self, s):
        p, S = self.packet, self.TransactionState
        if p.pid == PID.DATA0 or p.pid == PID.DATA1:  # as expected, do not handle DATA2/MDATA
            if not self.handle_data_out_toggle(p):
                _dbg('WRONG DATA SYNC')
                return S.WAIT_TOKEN
            else:  # data01 is ok
                # if this was last packet go back to waiting for token
                if self.received_data_callback(p):
                    # TODO: what if host does not receive ACK and sends data once again?
                    self.send_to_host(handshake_packet(PID.ACK))
                    return S.WAIT_TOKEN
                else:  # we need to handle more data
                    return S.WAIT_DATA_OUT
        else:
            # error
            return S.WAIT_TOKEN

    def on_wait_handshake(self, s):
        p, S = self.packet, self.TransactionState
        if p.pid == PID.ACK:
            if self.ack_callback:
                self.ack_callback(p.pid)
            return S.WAIT_TOKEN
        elif p.pid == PID.NAK:
            # send data once again self.to_send should not be cleared in expect...
            # expect_device_packet will be called once again sending self.to_send
            return S.WAIT_HANDSHAKE_OUT
        elif p.pid == PID.STALL:
            raise ValueError('Host STALL not allowed')
            return S.WAIT_TOKEN  # in theory we would do that
        else:
            # error
            return S.WAIT_TOKEN

    def handle_sof(self):
        # update USBFRAMEH:L (FIXME: should also be incremented on missing/garbled frames, see docs)
        self.set_csr('usbframeh', msb(self.packet.framenum))
        self.set_csr('usbframel', lsb(self.packet.framenum))
        # generate interrupt
        self.assert_interrupt(self.IRQ.SOF)

    def handle_token_out(self):
        p = self.packet
        if p.pid == PID.SETUP:
            assert p.endp == 0
            # interrupt generated after successful SETUP packet
            self.assert_interrupt(self.IRQ.SUTOK)
            # update ep status
            self.update_csr('ep0cs', setbits=[7], clearbits=[1, 0])

            # clear data toggle
            # data toggle should be reset when receiveing SETUP packet (USB 2.0, 8.6.1)
            i = ep2toggle_index(0)
            self.dut.togctl_toggles = bitupdate(self.dut.togctl_toggles, clearbits=[i])

            def handle_setupdat(p):
                self.set_csr('setupdat', setupdat_bytes_to_csr(p.data), immediate=True)
                # interrupt and acknowledge
                self.assert_interrupt(self.IRQ.SUDAV)

                # FX2 handles only SET_ADDRESS request in hardware (TRM 2.3)
                # TODO: when setting address we should wait until status stage ACK completes!
                #       then uncomment code in handle_packet
                if p.data[0] == 0x00 and p.data[1] == 0x05:
                    adr = word(p.data[3], p.data[2])
                    assert adr < 0x80, 'USB device address should have 7 bits'
                    self.set_csr('fnaddr', adr)
                    # automatically ack
                    self.update_csr('ep0cs', clearbits=[7])

                length = word(p.data[7], p.data[6])
                is_data_dev2host = testbit(p.data[0], 7)
                if not is_data_dev2host or length == 0:  # data OUT/no data -> status IN
                    self.ctrl_transfer = self.ControlTransferType.STATUS_IN
                else:  # data IN, so status OUT
                    self.ctrl_transfer = self.ControlTransferType.STATUS_OUT
                _dbg('self.ctrl_transfer := ', self.ctrl_transfer)

                return True  # setup has always only one data packet

            # during this callback we are sure that we have DATA0/DATA1
            self.received_data_callback = handle_setupdat

        elif p.pid == PID.OUT:
            # handler called for data packet, returns True when all data has been received
            def handle_data(p):
                _dbg('handle_data: tep = %s, ctrl_transfer = %s' % (self.token_packet.endp, self.ctrl_transfer))
                if self.token_packet.endp == 0 and self.ctrl_transfer == self.ControlTransferType.STATUS_OUT:
                    # we are in control trasfer IN, status stage
                    assert p.pid == PID.DATA1, 'Status packet should always have DATA1'
                    assert len(p.data) == 0, 'Status packet should be empty'

                    # send status stage handshake
                    hsnak = testbit(self.get_csr('ep0cs'), 7)
                    stall = testbit(self.get_csr('ep0cs'), 0)
                    if hsnak:
                        self.send_to_host(handshake_packet(PID.NAK))
                    elif stall:
                        self.send_to_host(handshake_packet(PID.STALL))
                        # clear stall (EP0 should stall once)
                        self.update_csr('ep0cs', clearbits=[0])
                    else:
                        self.send_to_host(handshake_packet(PID.ACK))
                        # control transfer finished
                        self.ctrl_transfer = None; _dbg('* ctrl_transfer = None')


                elif self.token_packet.endp == 0:
                    # we are in control trasfer OUT, data stage
                    raise NotImplementedError('Data OUT handling for control trasnfers OUT')
                else:
                    raise NotImplementedError('Data OUT handling for endpoints other than EP0')

                return True # all data received
            self.received_data_callback = handle_data

        else:
            raise ValueError(p.pid)

    def handle_token_in(self):
        ep = self.packet.endp
        io = 1 # IN because it's "handle_token_in"

        toggle = testbit(self.dut.togctl_toggles, ep2toggle_index(ep, io))
        data_pid = PID.DATA1 if toggle else PID.DATA0

        # check if this IN transfer is a status stage of control transfer,
        print('  handle_token_in:self.ctrl_transfer', end=' '); __import__('pprint').pprint(self.ctrl_transfer)
        is_status_stage = ep == 0 and self.ctrl_transfer == self.ControlTransferType.STATUS_IN
        if is_status_stage:
            # send status stage handshake instead of data it it is NAK/STALL
            hsnak = testbit(self.get_csr('ep0cs'), 7)
            stall = testbit(self.get_csr('ep0cs'), 0)
            if hsnak:
                self.send_to_host(handshake_packet(PID.NAK))
                return False
            elif stall:
                # clear stall (EP0 should stall once)
                self.update_csr('ep0cs', clearbits=[0])
                self.send_to_host(handshake_packet(PID.STALL))
                return False
            else:
                # send empty data packet which means ACK
                # STATUS stage always has DATA1 (USB 2.0, 8.5.3)
                self.send_to_host(data_packet(PID.DATA1, []))
                # no need to toggle data bit on ACK as status has always DATA1 (?)
                self.ack_callback = None
                # control transfer finished
                self.ctrl_transfer = None; _dbg('* ctrl_transfer = None')
                return True  # wait for ACK

        count = 0
        def expect_data_callback():
            length = self.armed_ep_lengths[ep]
            if length is None and not is_status_stage:
                return None

            # at this moment we need one more cycle so that endpoint data gets propagated correclty
            # FIXME: rewrite this to advance simulation after writing to ep buffer, instead of this counter
            nonlocal count
            if count == 0:
                count += 1
                return None

            # be sure to disarm the endpoint
            self.armed_ep_lengths[ep] = None

            if ep == 0:
                # we are sending data IN in control transfer IN
                assert self.ctrl_transfer == self.ControlTransferType.STATUS_OUT, \
                    'Sending IN data on EP0, so this should be a control transfer with STATUS_OUT'

                origin = _ram_areas['ep0inout'][0]
                data = [xram_mem_get(self.dut, origin + i) for i in range(length)]

                _dbg('expect_data_callback/handle_token_in: data = %s' % data)
                self.send_to_host(data_packet(data_pid, data))

                def ack_callback(pid):
                    if pid == PID.ACK:
                        self.toggle_data_sync_bit(ep, io)
                self.ack_callback = ack_callback
            else:
                raise NotImplementedError('Endpoints other than 0 not implemented')

            return None  # send_to_host() will change expect_data_callback to a new one

        _dbg('handle_token_in')
        self.expect_data_callback = expect_data_callback

    def handle_data_out_toggle(self, p):
        tp = self.token_packet
        ep = tp.endp
        io = 0 if tp.pid == PID.OUT or tp.pid == PID.SETUP else 1
        toggle = testbit(self.dut.togctl_toggles, ep2toggle_index(ep, io))
        ok = (toggle and p.pid == PID.DATA1) or (not toggle and p.pid == PID.DATA0)
        if ok:
            self.toggle_data_sync_bit(ep, io)
        return ok

    def toggle_data_sync_bit(self, ep, io):
        #  _dbg('toggle_data_sync_bit(%s, %s), self.dut.togctl_toggles = %s' \
        #       % (ep, io, self.dut.togctl_toggles))
        i = ep2toggle_index(ep, io)
        toggle = testbit(self.dut.togctl_toggles, i)
        if toggle:
            self.dut.togctl_toggles = bitupdate(self.dut.togctl_toggles, clearbits=[i])
        else:
            self.dut.togctl_toggles = bitupdate(self.dut.togctl_toggles, setbits=[i])

    ### CPU register access monitor ############################################

    def arm_endpoint(self, ep):
        _dbg('Arming endpoint %d' % ep)
        ep_len = lambda prefix: word(self.get_csr(prefix + 'h'), self.get_csr(prefix + 'l'))
        if ep == 0:
            length = ep_len('ep0bc')
            # see xram_access_handler, this needs to be be fixed
            if hasattr(self, '_force_length') and self._force_length is not None:
                length = self._force_length
                self._force_length = None
            self.armed_ep_lengths[0] = length
            self.update_csr('ep0cs', setbits=[1])
        else:
            raise NotImplementedError('Endpoints other than 0 not implemented')

    def xram_access_handler(self, access):
        if access.ack:
            # clear interrupt flags on writes instead of setting register value
            clear_on_write_regs = ['ibnirq', 'nakirq', 'usbirq', 'epirp', 'gpifirq',
                                   *('ep%dfifoirq' % i for i in [2, 4, 6, 8])]
            for reg in clear_on_write_regs:
                if reg in self.csrs.keys():  # only implemented registers
                    if access.adr == self.csrs[reg] and access.we:
                        # use the value that shows up on read signal as last register value
                        last_val = access.dat_r
                        # we can set the new value now, as at this moment value from wishbone bus
                        # has already been written
                        self.set_csr(reg, bitupdate(last_val, clear=access.dat_w))

            # automatic data copying when writing sudptrl
            if access.adr == self.csrs['sudptrl'] and access.we:
                #  _dbg('SUDPTRL')

                sdpauto = testbit(self.get_csr('sudptrctl'), 0)
                if sdpauto:  # TRM 2.3.4.1
                    # automatically read length from SETUPDAT
                    setupdat = setupdat_csr_to_bytes(self.get_csr('setupdat'))
                    wLength = word(setupdat[7], setupdat[6])
                    # ...and from in-memory descriptor
                    # the descriptor should be pointed to by sudptr
                    adr_in = word(self.get_csr('sudptrh'), self.get_csr('sudptrl'))
                    bLength = xram_mem_get(self.dut, adr_in)
                    # choose smaller length
                    length = min(wLength, bLength)
                    # copy data to endpoint buffer
                    for i in range(length):
                        adr = _ram_areas['ep0inout'][0] + i
                        xram_mem_set(self.dut, adr, xram_mem_get(self.dut, adr_in + i))

                    # update length
                    self.set_csr('ep0bch', msb(length), immediate=True)
                    self.set_csr('ep0bcl', lsb(length), immediate=True)
                    self._force_length = length  # FIXME: we need to advance simulation or delay setting length

                # now just arm endpoint
                self.arm_endpoint(0)

            # endpoint arming TODO: rewrite this, its now obsolete
            if access.adr == self.csrs['ep0bcl'] and access.we:
                #  _dbg('EP0BCL')
                self.arm_endpoint(0)

        # even without ack handle autopointers
        self.autopointers.handle_xram_access(access)

    def sfr_access_handler(self, access):
        self.autopointers.handle_sfr_access(access)

    ### Interface to host ######################################################

    @cocotb.coroutine
    def receive_host_packet(self, packet):
        p = decode_packet(packet)
        self.handle_packet(p)
        yield ClockCycles(self.dut.sys_clk, 1)

    @cocotb.coroutine
    def expect_device_packet(self, timeout):
        data = None

        @cocotb.coroutine
        def wait_data_to_send():
            yield ClockCycles(self.dut.sys_clk, 1)
            nonlocal data
            while data is None:
                if self.expect_data_callback is not None:
                    data = self.expect_data_callback()
                yield ClockCycles(self.dut.sys_clk, 1)

        #  #  timer = Timer(timeout // 100)  # 10us, faster debugging
        timer = Timer(timeout // 10)  # 10us, faster debugging
        #  timer = Timer(timeout)
        yield [timer, wait_data_to_send()]

        if data is not None:
            self.expect_data_callback = None
            packet = data
            # simulate sending time
            yield ClockCycles(self.dut.sys_clk, len(wrap_packet(packet)))
            return packet
        else:
            #  yield Timer(timeout)
            #  yield Timer(timeout // 100)  # 10us, faster debugging
            return None
