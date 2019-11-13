from cocotb.monitors import BusMonitor
from cocotb.decorators import coroutine
from cocotb.triggers import RisingEdge, Timer
from cocotb.result import TestFailure

from cocotb_usb.usb.packet import sync, eop, nrzi


class UsbMonitor(BusMonitor):
    """USB bus monitor.

    Listens for SYNC token then tries to capture the following frame up to EOP.

    Args:
        oversampling (int): How many times the signal is sampled on each cycle.
    """
    # Internal states
    (IDLE, PRIMED, RECEIVING) = range(3)

    def __init__(self, *args, **kwargs):
        self.cycles = kwargs.pop('oversampling', 4)
        self.clock_period = kwargs.pop('clk_period', 20830)  # 48 MHz

        self.dut = args[0]
        BusMonitor.__init__(self, *args, **kwargs)
        self.state = self.IDLE

    def prime(self):
        """Notify the object that a transaction is expected"""
        self.state = self.PRIMED

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

        # We want to sample in the middle of a signal to allow for jitter
        t_middle = Timer(self.clock_period // 4, 'ps')
        bit_time_max = 12.5
        bit_time_acceptable = 7.5
        while True:
            yield RisingEdge(self.clock)
            yield t_middle
            if self.in_reset:
                continue

            # If someone is waiting for response, measure bit times
            if self.state == self.PRIMED:
                bit_time += 1
                self.dut._log.debug(f"Waiting, bit time {bit_time/4 -8}")
                if (bit_time / 4.0) > bit_time_max + len(SYNC)/4:
                    self.dut._log.error(
                        "No data after {} bit times, which is more than {}".
                        format(bit_time / 4.0 - 8, bit_time_max))
                    raise TestFailure()

            pkt += current()

            if self.state == self.PRIMED and pkt == SYNC:
                # Start monitoring
                self.state = self.RECEIVING
                self.dut._log.debug("Got SYNC")
                if (bit_time / 4.0) > bit_time_acceptable + len(SYNC)/4:
                    self.dut._log.warn(
                        "No data after {} bit times (> {})".format(
                            bit_time / 4.0 - 8, bit_time_acceptable))
                else:
                    self.dut._log.info("Response came after {} bit times"
                                       .format((bit_time - len(SYNC)) / 4.0))
                bit_time = 0
                continue
            elif self.state == self.RECEIVING and (pkt[-len(EOP):] == EOP):
                # Pass the packet to listeners
                self.dut._log.debug("Got EOP")
                self.dut._log.debug("Current packet: [{}]".format(pkt))
                self._recv(pkt)
                pkt = ""
                self.state = self.IDLE
            elif (self.state != self.RECEIVING) and (len(pkt) >= len(SYNC)):
                # Full window and nothing detected, slide it
                pkt = pkt[1:]
            else:
                # We're still gathering samples...
                continue
