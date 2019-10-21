from struct import pack
from . import USBDeviceRequest

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


class DfuFunctionalDescriptor:
    TYPE = 0x21
    FORMAT = "<3B3W"

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

    def get(self):
        """Return descriptor contents as list of bytes"""
        return [
                self.bLength,
                self.bDescriptorType,
                self.bmAttributes,
                self.wDetachTimeout & 0x00FF,
                self.wDetachTimeout >> 8,
                self.wTransferSize & 0x00FF,
                self.wTransferSize >> 8,
                self.bcdDFUVersion & 0x00FF,
                self.bcdDFUVersion >> 8
        ]

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
