from os import environ
from cocotb_usb.host import UsbTest
from cocotb_usb.host_valenty import UsbTestValenty
from cocotb_usb.host_fx2 import UsbTestFX2

TARGET = environ.get('TARGET')


def get_harness(dut, **kwargs):
    '''
    Helper function to assign test harness object.
    Object is chosen using ``TARGET`` environment variable.
    '''
    if TARGET == 'valentyusb':
        dut_csrs = environ['DUT_CSRS']  # We want a KeyError if this is unset
        harness = UsbTestValenty(dut, dut_csrs, **kwargs)
    elif TARGET == 'fx2':
        dut_csrs = environ['DUT_CSRS']  # We want a KeyError if this is unset
        harness = UsbTestFX2(dut, dut_csrs, **kwargs)
    else:  # No target matched
        harness = UsbTest(dut, **kwargs)  # base class
    return harness
