from cocotb.monitors import BusMonitor
from cocotb.decorators import coroutine
from cocotb.triggers import RisingEdge
from cocotb.result import TestFailure

from cocotb_usb.usb.packet import sync, eop, nrzi


class UsbMonitor(BusMonitor):
    """USB bus monitor.

    Listens for SYNC token then tries to capture the following frame up to EOP.

    Args:
        oversampling (int): #TODO
    """
    def __init__(self, *args, **kwargs):
        self.cycles = kwargs.pop('oversampling', 4)
        self.dut = kwargs.pop('dut')
        BusMonitor.__init__(self, *args, **kwargs)

    @coroutine
    def _monitor_recv(self):
        pkt = ""
        SYNC = nrzi(sync(), cycles=self.cycles)
        EOP = nrzi(eop(), cycles=self.cycles)
        bit_time = 0

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

        rcv = False
        while True:
            yield RisingEdge(self.clock)
            if self.in_reset:
                continue

            pkt += current()
            if pkt == SYNC:
                # Start monitoring
                rcv = True
                self.dut._log.debug("Got SYNC")
                continue
            elif (pkt[-len(EOP):] == EOP):
                # Pass the packet to listeners
                self.dut._log.debug("Got EOP")
                self.dut._log.debug("Current packet: [{}]".format(pkt))
                self._recv(pkt)
                pkt = ""
                bit_time = 0
                rcv = False
            elif (not rcv) and (len(pkt) >= len(SYNC)):
                # Full window and nothing detected, slide it
                bit_time += 1
                pkt = pkt[1:]
            else:
                # We're still gathering samples...
                bit_time += 1
                continue
