import csv
from cocotb.result import TestFailure


def grouper_tofit(n, iterable):
    from itertools import zip_longest
    """Group iterable into multiples of n, except don't leave
    trailing None values at the end.
    """
    # itertools.zip_longest is broken because it requires you to fill in some
    # value, and doesn't mention anything else in its documentation that would
    # not require this behavior.
    # Re-do the array to shrink it down if any None values are discovered.
    broken = zip_longest(*[iter(iterable)] * n, fillvalue=None)
    fixed = []
    for e in broken:
        f = []
        for el in e:
            if el is not None:
                f.append(el)
        fixed.append(f)
    return fixed


def parse_csr(csr_file="csr.csv"):
    csrs = dict()
    with open(csr_file, newline='') as csr_csv_file:
        csr_csv = csv.reader(csr_csv_file)
        # csr_register format: csr_register, name, address, size, rw/ro
        for row in csr_csv:
            if row[0] == 'csr_register':
                csrs[row[1]] = int(row[2], base=0)
    return csrs


def assertEqual(a, b, msg):
    if a != b:
        raise TestFailure("{} vs {} - {}".format(a, b, msg))
