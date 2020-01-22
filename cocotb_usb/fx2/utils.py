import os
from functools import reduce


def _dbg(*args):
    if os.environ.get('FX2DEBUG', 0) == '1':
        bold_white = '\033[1;37m'
        clear = '\033[0m'
        print(bold_white + '  ', end='')
        print(args[0], end=clear)
        print('', *args[1:])


def bit(n):
    return 1 << int(n)


def testbit(val, n):
    return (int(val) & bit(n)) != 0


def msb(word):
    return (0xff00 & int(word)) >> 8


def lsb(word):
    return 0xff & int(word)


def word(msb, lsb):
    return ((int(msb) & 0xff) << 8) | (int(lsb) & 0xff)


def bitupdate(reg, *, set=None, clear=None, clearbits=None, setbits=None):
    """
    Convenience function for bit manipulations.

    reg:       original value
    set:       bitmask of values to be set
    clear:     bitmask of values to be cleared
    setbits:   list of bit offsets to use for constructing `set` mask (`set`
               must be None)
    clearbits: list of bit offsets to use for constructing `clear` mask
               (`clear` must be None)
    """
    # convert bit lists to masks
    def bitsmask(bits):
        return reduce(lambda p, q: p | q, ((1 << b) for b in bits))

    if clearbits:
        assert clear is None, "'clear' must not be used when using 'clearbits'"
        clear = bitsmask(clearbits)
    if setbits:
        assert set is None, "'set' must not be used when using 'setbits'"
        set = bitsmask(setbits)
    # set default values, assert when nothing happens
    # (we don't use this function if need no change)
    assert set is not None or clear is not None, 'Nothing to set/clear'
    set = 0 if set is None else set
    clear = 0 if clear is None else clear
    # clear and set mask overlap
    assert (set & clear) == 0, \
        'Bit masks overlap: set(%s) clear(%s)' % (bin(set), bin(clear))
    # perform bit operation
    reg = (int(reg) & (~clear)) | set
    return reg
