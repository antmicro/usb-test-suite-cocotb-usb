import json

from .usb.descriptors import (EndpointDescriptor, InterfaceDescriptor,
                              ConfigDescriptor, DeviceDescriptor,
                              StringDescriptorZero, StringDescriptor,
                              DeviceQualifierDescriptor)
from .usb.class_specific.dfu import DfuFunctionalDescriptor


def getVal(val, minimum, maximum, isHexString=False):
    '''Helper function to get values in given range'''
    if isHexString:
        val = int(val, base=16)
    if not minimum <= val <= maximum:
        raise ValueError()
    return val


class UsbJsonParser():
    '''Parser to retrieve USB descriptors from a JSON file'''
    def __init__(self, config_file):
        with open(config_file, "r") as f:
            self.data = json.load(f)

    def parseEndpoint(self, e):
        bLength = getVal(e["bLength"], 0, 0xFF)

        if e["bEndpointAddress"][1] == "IN":
            endpointDir = EndpointDescriptor.Direction.IN
        elif e["bEndpointAddress"][1] == "OUT":
            endpointDir = EndpointDescriptor.Direction.OUT
        bEndpointAddress = getVal(e["bEndpointAddress"][0], 0,
                                  15) | (endpointDir << 7)

        if e["bmAttributes"]["Transfer"] == "Control":
            eTransfer = EndpointDescriptor.TransferType.CONTROL
        elif e["bmAttributes"]["Transfer"] == "Isochronous":
            eTransfer = EndpointDescriptor.TransferType.ISOCHRONOUS
        elif e["bmAttributes"]["Transfer"] == "Bulk":
            eTransfer = EndpointDescriptor.TransferType.BULK
        elif e["bmAttributes"]["Transfer"] == "Interrupt":
            eTransfer = EndpointDescriptor.TransferType.INTERRUPT

        if e["bmAttributes"]["Synch"] == "None":
            eSynch = EndpointDescriptor.SynchronizationType.NO
        elif e["bmAttributes"]["Synch"] == "Asynchronous":
            eSynch = EndpointDescriptor.SynchronizationType.ASYNC
        elif e["bmAttributes"]["Synch"] == "Adaptive":
            eSynch = EndpointDescriptor.SynchronizationType.ADAPTIVE
        elif e["bmAttributes"]["Synch"] == "Synchronous":
            eSynch = EndpointDescriptor.SynchronizationType.SYNC

        if e["bmAttributes"]["Usage"] == "Data":
            eUsage = EndpointDescriptor.UsageType.DATA
        elif e["bmAttributes"]["Usage"] == "Feedback":
            eUsage = EndpointDescriptor.UsageType.FEEDBACK
        elif e["bmAttributes"]["Usage"] == "Implicit feedback Data":
            eUsage = EndpointDescriptor.UsageType.IFDATA
        bmAttributes = eUsage << 5 | eSynch << 3 | eTransfer

        # Bits 15..13 must be set to zero below
        wMaxPacketSize = getVal(e["wMaxPacketSize"], 0, 0x1FFF, True)
        bInterval = getVal(e["bInterval"], 0, 0xFF)

        return EndpointDescriptor(bLength, bEndpointAddress, bmAttributes,
                                  wMaxPacketSize, bInterval)

    def parseDfuFunctional(self, f):
        return DfuFunctionalDescriptor(
            bLength=getVal(f["bLength"], 0, 0xFF),
            bDescriptorType=getVal(f["bDescriptorType"], 0, 0xFF),
            bmAttributes=getVal(f["bmAttributes"], 0, 0xFF, True),
            wDetachTimeout=getVal(f["wDetachTimeout"], 0, 0xFFFF),
            wTransferSize=getVal(f["wTransferSize"], 0, 0xFFFF),
            bcdDFUVersion=getVal(f["bcdDFUVersion"], 0, 0xFFFF, True)
            )

    def parseDescriptor(self, field):
        descriptor = None
        if field["name"] == "DFU Functional":
            descriptor = self.parseDfuFunctional(field)
        elif field["name"] == "Endpoint":
            descriptor = self.parseEndpoint(field)
        return descriptor

    def parseInterface(self, intf):
        sub_list = [self.parseDescriptor(e) for e in intf["Subdescriptors"]]
        return InterfaceDescriptor(
            bLength=getVal(intf["bLength"], 0, 0xFF),
            bInterfaceNumber=getVal(intf["bInterfaceNumber"], 0, 0xFF),
            bAlternateSetting=getVal(intf["bAlternateSetting"], 0, 0xFF),
            bNumEndpoints=getVal(intf["bNumEndpoints"], 0, 0xFF),
            bInterfaceClass=getVal(intf["bInterfaceClass"], 0, 0xFF),
            bInterfaceSubclass=getVal(intf["bInterfaceSubClass"], 0, 0xFF),
            bInterfaceProtocol=getVal(intf["bInterfaceProtocol"], 0, 0xFF),
            iInterface=getVal(intf["iInterface"], 0, 0xFF),
            subdescriptors=sub_list)

    def getDeviceDescriptor(self):
        return DeviceDescriptor(
            bLength=getVal(self.data["Device"]["bLength"], 0, 0xFF),
            bDescriptorType=getVal(self.data["Device"]["bDescriptorType"], 1,
                                   1),
            bcdUSB=getVal(self.data["Device"]["bcdUSB"], 0, 0xFFFF, True),
            bDeviceClass=getVal(self.data["Device"]["bDeviceClass"], 0, 0xFF),
            bDeviceSubClass=getVal(self.data["Device"]["bDeviceSubClass"], 0,
                                   0xFF),
            bDeviceProtocol=getVal(self.data["Device"]["bDeviceProtocol"], 0,
                                   0xFF),
            bMaxPacketSize0=getVal(self.data["Device"]["bMaxPacketSize0"], 0,
                                   0xFF),
            idVendor=getVal(self.data["Device"]["idVendor"], 0, 0xFFFF, True),
            idProduct=getVal(self.data["Device"]["idProduct"], 0, 0xFFFF,
                             True),
            bcdDevice=getVal(self.data["Device"]["bcdDevice"], 0, 0xFFFF,
                             True),
            iManufacturer=getVal(self.data["Device"]["iManufacturer"], 0,
                                 0xFF),
            iProduct=getVal(self.data["Device"]["iProduct"], 0, 0xFF),
            iSerialNumber=getVal(self.data["Device"]["iSerial"], 0, 0xFF),
            bNumConfigurations=getVal(
                self.data["Device"]["bNumConfigurations"], 0, 0xFF))

    def getConfigurationDescriptor(self, idx):
        idx = str(idx)
        assert idx in self.data["Configuration"].keys()
        interface_list = [
            self.parseInterface(i)
            for i in self.data["Configuration"][idx]["Interface"]
        ]
        return ConfigDescriptor(
            bLength=getVal(self.data["Configuration"][idx]["bLength"], 0,
                           0xFF),
            bDescriptorType=getVal(
                self.data["Configuration"][idx]["bDescriptorType"], 2, 2),
            wTotalLength=getVal(
                self.data["Configuration"][idx]["wTotalLength"], 0, 0xFFFF),
            bNumInterfaces=getVal(
                self.data["Configuration"][idx]["bNumInterfaces"], 0, 0xFF),
            bConfigurationValue=getVal(
                self.data["Configuration"][idx]["bConfigurationValue"], 0,
                0xFF),
            iConfiguration=getVal(
                self.data["Configuration"][idx]["iConfiguration"], 0, 0xFF),
            bmAttributes=getVal(
                self.data["Configuration"][idx]["bmAttributes"], 0, 0xFF,
                True),
            bMaxPower=getVal(self.data["Configuration"][idx]["bMaxPower"], 0,
                             0xFF),
            interfaces=interface_list)

    def getStringDescriptorZero(self):
        # Device can omit all string descriptors
        if len(self.data["String"]) > 0:
            # At index 0 we expect an array of LangId codes
            langIdArray = [int(i, base=16) for i in self.data["String"][0]]
            return StringDescriptorZero(langIdArray)
        else:
            return StringDescriptorZero([])

    def getStringDescriptors(self):
        descriptors = dict()
        if len(self.data["String"]) > 0:
            # We expect strings for every reported LangId.
            # No strings for a LangId will raise a KeyError
            for lid in self.data["String"][0]:
                lid_descriptors = [
                    StringDescriptor(s) for s in self.data["String"][1][lid]
                ]
                descriptors[int(lid, base=16)] = lid_descriptors

        return descriptors

    def getDeviceQualifierDescriptor(self):
        return DeviceQualifierDescriptor(
            bLength=getVal(self.data["Device Qualifier"]["bLength"], 0, 0xFF),
            bDescriptorType=getVal(
                self.data["Device Qualifier"]["bDescriptorType"], 0, 0xFF),
            bcdUSB=getVal(self.data["Device Qualifier"]["bcdUSB"], 0, 0xFFFF,
                          True),
            bDeviceClass=getVal(self.data["Device Qualifier"]["bDeviceClass"],
                                0, 0xFF),
            bDeviceSubClass=getVal(
                self.data["Device Qualifier"]["bDeviceSubClass"], 0, 0xFF),
            bDeviceProtocol=getVal(
                self.data["Device Qualifier"]["bDeviceProtocol"], 0, 0xFF),
            bMaxPacketSize0=getVal(
                self.data["Device Qualifier"]["bMaxPacketSize0"], 0, 0xFF),
            bNumConfigurations=getVal(
                self.data["Device Qualifier"]["bNumConfigurations"], 0, 0xFF),
        )


class UsbDevice:
    '''Object for storing USB descriptors information in a structured manner'''
    def __init__(self, config_file):
        parser = UsbJsonParser(config_file)
        self.deviceDescriptor = parser.getDeviceDescriptor()
        self.configDescriptor = dict()
        for i in range(1, self.deviceDescriptor.bNumConfigurations + 1):
            descriptor = parser.getConfigurationDescriptor(i)
            self.configDescriptor[i] = descriptor

        self.stringDescriptorZero = parser.getStringDescriptorZero()
        self.stringDescriptor = parser.getStringDescriptors()

        try:
            self.deviceQualifierDescriptor = \
                    parser.getDeviceQualifierDescriptor()
        except KeyError as e:
            if e.args[0] == "Device Qualifier":
                # Pre-USB2.0 devices do not need to implement device qualifier
                self.deviceQualifierDescriptor = None
            else:
                raise e
