import json

from .usb.descriptors import *

def getVal(val, minimum, maximum, isHexString = False):
    if isHexString:
        val = int(val, base = 16)
    if not minimum <= val <= maximum:
        raise ValueError()
    return val

class UsbJsonParser():
    def __init__(self, config_file):
        with open(config_file, "r") as f:
            self.data = json.load(f)

    def getDeviceDescriptor(self):
        return DeviceDescriptor(
            bLength            = getVal(self.data["Device"]["bLength"], 0, 0xFF),
            bDescriptorType    = getVal(self.data["Device"]["bDescriptorType"], 1, 1),
            bcdUSB             = getVal(self.data["Device"]["bcdUSB"], 0, 0xFFFF, True),
            bDeviceClass       = getVal(self.data["Device"]["bDeviceClass"], 0, 0xFF),
            bDeviceSubClass    = getVal(self.data["Device"]["bDeviceSubClass"], 0, 0xFF),
            bDeviceProtocol    = getVal(self.data["Device"]["bDeviceProtocol"], 0, 0xFF),
            bMaxPacketSize0    = getVal(self.data["Device"]["bMaxPacketSize0"], 0, 0xFF),
            idVendor           = getVal(self.data["Device"]["idVendor"], 0, 0xFFFF, True),
            idProduct          = getVal(self.data["Device"]["idProduct"], 0, 0xFFFF, True),
            bcdDevice          = getVal(self.data["Device"]["bcdDevice"], 0, 0xFFFF, True),
            iManufacturer      = getVal(self.data["Device"]["iManufacturer"], 0, 0xFF),
            iProduct           = getVal(self.data["Device"]["iProduct"], 0, 0xFF),
            iSerialNumber      = getVal(self.data["Device"]["iSerial"], 0, 0xFF),
            bNumConfigurations = getVal(self.data["Device"]["bNumConfigurations"], 0, 0xFF)
            )

    def getConfigurationDescriptor(self, idx):
        idx = str(idx)
        assert idx in self.data["Configuration"].keys()
        return ConfigDescriptor(
            bLength             =  getVal(self.data["Configuration"][idx]["bLength"], 0, 0xFF),
            bDescriptorType     =  getVal(self.data["Configuration"][idx]["bDescriptorType"], 2, 2),
            wTotalLength        =  getVal(self.data["Configuration"][idx]["wTotalLength"], 0, 0xFFFF),
            bNumInterfaces      =  getVal(self.data["Configuration"][idx]["bNumInterfaces"], 0, 0xFF),
            bConfigurationValue =  getVal(self.data["Configuration"][idx]["bConfigurationValue"], 0, 0xFF),
            iConfiguration      =  getVal(self.data["Configuration"][idx]["iConfiguration"], 0, 0xFF),
            bmAttributes        =  getVal(self.data["Configuration"][idx]["bmAttributes"], 0, 0xFF, True),
            bMaxPower           =  getVal(self.data["Configuration"][idx]["bMaxPower"], 0, 0xFF)
            )

    def getStringDescriptorZero(self):
        # Device can omit all string descriptors
        if len(self.data["String"]) > 0:
            # At index 0 we expect an array of LangId codes
            langIdArray = [int(i, base = 16) for i in self.data["String"][0]]
            return StringDescriptorZero(langIdArray)
        else:
            return StringDescriptorZero([])

    def getStringDescriptors(self):
        descriptors = dict()
        if len(self.data["String"]) > 0:
            # We expect strings for every reported LangId. No strings for a LangId will raise a KeyError
            for lid in self.data["String"][0]:
                lid_descriptors = [StringDescriptor(s) for s in self.data["String"][1][lid]]
                descriptors[int(lid, base = 16)] = lid_descriptors

        return descriptors


class UsbDevice:
    def __init__(self, config_file):
        parser = UsbJsonParser(config_file)
        self.deviceDescriptor = parser.getDeviceDescriptor()
        self.configDescriptor = []
        for i in range(1,self.deviceDescriptor.bNumConfigurations + 1):
            descriptor = parser.getConfigurationDescriptor(i)
            self.configDescriptor.append(descriptor)

        self.stringDescriptorZero = parser.getStringDescriptorZero()
        self.stringDescriptor = parser.getStringDescriptors()

