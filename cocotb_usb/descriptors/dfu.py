from struct import pack
from . import Descriptor, USBDeviceRequest
from ..utils import getVal

DFU_CLASS_CODE = 0xFE       # Application specific class code
DFU_SUBCLASS_CODE = 0x01    # Device Firmware Update code
DFU_INTERFACE_PROTOCOL = 0x02


class DfuAttributes:
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
        return pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.bmAttributes,
                    self.wDetachTimeout,
                    self.wTransferSize,
                    self.bcdDFUVersion)


class DfuRequest(USBDeviceRequest):
    class Type:
        DFU_DETACH = 0
        DFU_DNLOAD = 1
        DFU_UPLOAD = 2
        DFU_GETSTATUS = 3
        DFU_CLRSTATUS = 4
        DFU_GETSTATE = 5
        DFU_ABORT = 6


def parseDfuFunctional(f):
    return DfuFunctionalDescriptor(
        bLength=getVal(f["bLength"], 0, 0xFF),
        bDescriptorType=getVal(f["bDescriptorType"], 0, 0xFF),
        bmAttributes=getVal(f["bmAttributes"], 0, 0xFF),
        wDetachTimeout=getVal(f["wDetachTimeout"], 0, 0xFFFF),
        wTransferSize=getVal(f["wTransferSize"], 0, 0xFFFF),
        bcdDFUVersion=getVal(f["bcdDFUVersion"], 0, 0xFFFF)
        )


dfuParsers = {DfuFunctionalDescriptor.TYPE: parseDfuFunctional}
