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

        self.dut = args[0]
        BusMonitor.__init__(self, *args, **kwargs)
        self.primed = False

    def prime(self):
        """Notify the object that a transaction is expected"""
        self.primed = True

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

            # If someone is waiting for response, measure bit times
            if self.primed and not rcv:
                bit_time += 1
                self.dut._log.debug(f"Waiting, bit time {bit_time//4}")
                bit_time_max = 12.5
                bit_time_acceptable = 7.5
                if (bit_time / 4.0) > bit_time_max + len(SYNC)/4:
                    self.dut._log.error(
                        "No data after {} bit times, which is more than {}".
                        format(bit_time / 4.0, bit_time_max))
                if (bit_time / 4.0) > bit_time_acceptable + len(SYNC)/4:
                    self.dut._log.warn(
                        "No data after {} bit times (> {})".format(
                            bit_time / 4.0, bit_time_acceptable))
            pkt += current()
            if self.primed and pkt == SYNC:
                # Start monitoring
                rcv = True
                self.dut._log.info("Got SYNC")
                self.dut._log.info("Response came after {} bit times".format(
                        (bit_time - len(SYNC))/ 4.0))
                bit_time = 0
                continue
            elif rcv and (pkt[-len(EOP):] == EOP):
                # Pass the packet to listeners
                self.dut._log.info("Got EOP")
                self.dut._log.debug("Current packet: [{}]".format(pkt))
                self._recv(pkt)
                pkt = ""
                rcv = False
                self.primed = False
            elif (not rcv) and (len(pkt) >= len(SYNC)):
                # Full window and nothing detected, slide it
                pkt = pkt[1:]
            else:
                # We're still gathering samples...
                continue
