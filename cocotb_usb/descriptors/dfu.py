from struct import pack
from cocotb_usb.descriptors import Descriptor, USBDeviceRequest
from cocotb_usb.utils import getVal

DFU_CLASS_CODE = 0xFE       # Application specific class code
DFU_SUBCLASS_CODE = 0x01    # Device Firmware Update code
DFU_INTERFACE_PROTOCOL = 0x02


class DfuAttributes:
    """ Class for storing common DFU descriptor attributes."""

    # Bit 7..4: reserved
    class WillDetach:
        NO = 0 << 3
        YES = 1 << 3

    class ManifestationTolerant:
        NO = 0 << 2  # Must see bus reset
        YES = 1 << 2

    class CanUpload:
        NO = 0 << 1
        YES = 1 << 1

    class CanDnload:
        NO = 0 << 0
        YES = 1 << 0


class DfuFunctionalDescriptor(Descriptor):
    """Class for storing functional descriptor of DFU."""

    TYPE = 0x21
    FORMAT = "<3B3H"

    def __init__(self,
                 bmAttributes,
                 wDetachTimeout,
                 wTransferSize,
                 bcdDFUVersion,
                 bLength=0x09,
                 bDescriptorType=TYPE
                 ):
        self.bmAttributes = bmAttributes
        self.wDetachTimeout = wDetachTimeout
        self.wTransferSize = wTransferSize
        self.bcdDFUVersion = bcdDFUVersion
        self.bLength = bLength
        self.bDescriptorType = bDescriptorType

    def __bytes__(self):
        """
        >>> d = DfuFunctionalDescriptor(
        ... bmAttributes=0x0d,
        ... wDetachTimeout=10000,
        ... wTransferSize=1024,
        ... bcdDFUVersion=0x0101)
        >>> bytes(d)
        b"\\t!\\r\\x10'\\x00\\x04\\x01\\x01"
        >>> d.get()
        [9, 33, 13, 16, 39, 0, 4, 1, 1]
        """
        return pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.bmAttributes,
                    self.wDetachTimeout,
                    self.wTransferSize,
                    self.bcdDFUVersion)


class DfuRequest(USBDeviceRequest):
    """Base class for DFU requests."""
    class Type:
        DFU_DETACH = 0
        DFU_DNLOAD = 1
        DFU_UPLOAD = 2
        DFU_GETSTATUS = 3
        DFU_CLRSTATUS = 4
        DFU_GETSTATE = 5
        DFU_ABORT = 6


def parseDfuFunctional(f):
    """Parser function to read values of supported DFU descriptors for
    the device from config file.

    Args:
        field:  JSON structure for this class to be parsed.

    .. doctest:

        >>> f = {
        ... "name":     "DFU Functional",
        ... "bLength":                 9,
        ... "bDescriptorType":    "0x21",
        ... "bmAttributes":       "0x0D",
        ... "wDetachTimeout":      10000,
        ... "wTransferSize":        1024,
        ... "bcdDFUVersion":    "0x0101"
        ... }
        >>> d = parseDfuFunctional(f)
        >>> d.get()
        [9, 33, 13, 16, 39, 0, 4, 1, 1]
    """
    return DfuFunctionalDescriptor(
        bLength=getVal(f["bLength"], 0, 0xFF),
        bDescriptorType=getVal(f["bDescriptorType"], 0, 0xFF),
        bmAttributes=getVal(f["bmAttributes"], 0, 0xFF),
        wDetachTimeout=getVal(f["wDetachTimeout"], 0, 0xFFFF),
        wTransferSize=getVal(f["wTransferSize"], 0, 0xFFFF),
        bcdDFUVersion=getVal(f["bcdDFUVersion"], 0, 0xFFFF)
        )


dfuParsers = {DfuFunctionalDescriptor.TYPE: parseDfuFunctional}

if __name__ == "__main__":
    import doctest
    doctest.testmod()
