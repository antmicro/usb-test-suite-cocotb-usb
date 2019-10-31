import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, GPITrigger, TriggerException, _wait_callback
from cocotb.utils import get_sim_steps, get_time_from_sim_steps

import os
from random import randint
import itertools

if "COCOTB_SIM" in os.environ:
    import simulator
else:
    simulator = None


class UnstableTrigger(GPITrigger):
    """A trigger with uncertainty within defined range."""
    def __init__(self, time_ps, delta_neg, delta_pos, units=None):
        GPITrigger.__init__(self)
        self.sim_steps = get_sim_steps(time_ps, units)
        self.delta_neg = delta_neg
        self.delta_pos = delta_pos

    def prime(self, callback):
        """Register for a timed callback."""
        steps = self.sim_steps + randint(-self.delta_neg, self.delta_pos)
        if self.cbhdl == 0:
            self.cbhdl = simulator.register_timed_callback(
                steps, callback, self)
            if self.cbhdl == 0:
                raise TriggerException("Unable set up %s Trigger" %
                                       (str(self)))
        GPITrigger.prime(self, callback)

    def __str__(self):
        return self.__class__.__name__ + "(%1.2fps)" % get_time_from_sim_steps(
            self.sim_steps, units='ps')


class UnstableClock(Clock):
    """A 50:50 duty cycle clock driver with added jitter.

    Args:
        signal: The clock pin/signal to be driven.
        period (int): The clock period. Must convert to an even number of
            timesteps.
        jitter_neg (int): Maximum negative jitter.
        jitter_pos (int): Maximum positive jitter.
        units (str, optional): One of
            ``None``, ``'fs'``, ``'ps'``, ``'ns'``, ``'us'``, ``'ms'``,
            ``'sec'``.
            When no *units* is given (``None``) the timestep is determined by
            the simulator.
    """
    def __init__(self, signal, period, jitter_neg, jitter_pos, units=None):
        super().__init__(signal, period, units)
        self.jitter_neg = jitter_neg
        self.jitter_pos = jitter_pos
        self.units = units

    @cocotb.coroutine
    def start(self, cycles=None, start_high=True):
        """Clocking coroutine. Start driving your clock by forking a
        call to this.

        Args:
            cycles (int, optional): Cycle the clock *cycles* number of times,
                or if ``None`` then cycle the clock forever.
                Note: ``0`` is not the same as ``None``, as ``0`` will cycle
                no times.
            start_high (bool, optional): Whether to start the clock with
                a ``1`` for the first half of the period.
                Default is ``True``.
        """
        # We need two objects to allow their periods to overlap
        u1 = UnstableTrigger(self.half_period, self.jitter_neg,
                             self.jitter_pos, self.units)
        u2 = UnstableTrigger(self.half_period, self.jitter_neg,
                             self.jitter_pos, self.units)

        t = Timer(self.half_period)

        if cycles is None:
            it = itertools.count()
        else:
            it = range(cycles)

        def strobeH(ret):
            self.signal <= 1

        def strobeL(ret):
            self.signal <= 0

        # branch outside for loop for performance
        if start_high:
            self.signal <= 1
            for _ in it:
                cocotb.fork(_wait_callback(u1, strobeL))
                yield t
                cocotb.fork(_wait_callback(u2, strobeH))
                yield t
        else:
            self.signal <= 0
            for _ in it:
                cocotb.fork(_wait_callback(u1, strobeH))
                yield t
                cocotb.fork(_wait_callback(u2, strobeL))
                yield t

    def __str__(self):
        return self.__class__.__name__ + "(%3.1f MHz)" % self.frequency
