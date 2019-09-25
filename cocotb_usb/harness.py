from os import environ
from .host import UsbTest, UsbTestValenty

TARGET = environ.get('TARGET')

def get_harness(dut, **kwargs):
    '''
    Helper function to assign test harness object based on TARGET environment variable
    '''
    if TARGET == 'valentyusb':
        dut_csrs = environ['DUT_CSRS'] # We want a KeyError if this is unset
        harness = UsbTestValenty(dut, dut_csrs, **kwargs)
    else: # No target matched
        harness = UsbTest(dut, **kwargs) # base class
    return harness
