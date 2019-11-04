import json
from cocotb_usb.descriptors import (Descriptor, EndpointDescriptor,
                                    InterfaceDescriptor,
                                    ConfigDescriptor, DeviceDescriptor,
                                    StringDescriptorZero, StringDescriptor,
                                    DeviceQualifierDescriptor)
from cocotb_usb.descriptors.dfu import DFU_CLASS_CODE, dfuParsers
from cocotb_usb.descriptors.cdc import CDC, cdcParsers
from cocotb_usb.utils import getVal


def isStandard(descriptorType):
    """
    >>> isStandard(0x0a)
    True
    >>> isStandard(0x22)
    False
    >>> isStandard(0x61)
    False
    >>> isStandard(0x1a)
    True
    """
    # See USB Common Class Specification s. 3.11 for this field's structure
    # Bit 7: reserved
    # Bits 6..5: descriptor type
    #            STANDARD = 0
    #            CLASS = 1
    #            VENDOR = 2
    #            RESERVED = 3
    # Bits 4..0: descriptor ID
    if ((descriptorType & 0b01100000) >> 5) == 0:
        return True
    else:
        return False


def parseDevice(field):
    """
    >>> f = {
    ... "name": "Device",
    ... "bLength":                18,
    ... "bDescriptorType":         1,
    ... "bcdUSB":           "0x0201",
    ... "bDeviceClass":            "0xef",
    ... "bDeviceSubClass":         2,
    ... "bDeviceProtocol":         1,
    ... "bMaxPacketSize0":        64,
    ... "idVendor":         "0x1209",
    ... "idProduct":        "0x5bf0",
    ... "bcdDevice":        "0x0101",
    ... "iManufacturer":           1,
    ... "iProduct":                2,
    ... "iSerial":                 0,
    ... "bNumConfigurations":      1
    ... }
    >>> d = parseDevice(f)
    >>> d.get()
    [18, 1, 1, 2, 239, 2, 1, 64, 9, 18, 240, 91, 1, 1, 1, 2, 0, 1]
    """
    return DeviceDescriptor(
        bLength=getVal(field["bLength"], 0, 0xFF),
        bDescriptorType=getVal(field["bDescriptorType"], 1, 1),
        bcdUSB=getVal(field["bcdUSB"], 0, 0xFFFF),
        bDeviceClass=getVal(field["bDeviceClass"], 0, 0xFF),
        bDeviceSubClass=getVal(field["bDeviceSubClass"], 0, 0xFF),
        bDeviceProtocol=getVal(field["bDeviceProtocol"], 0, 0xFF),
        bMaxPacketSize0=getVal(field["bMaxPacketSize0"], 0, 0xFF),
        idVendor=getVal(field["idVendor"], 0, 0xFFFF),
        idProduct=getVal(field["idProduct"], 0, 0xFFFF),
        bcdDevice=getVal(field["bcdDevice"], 0, 0xFFFF),
        iManufacturer=getVal(field["iManufacturer"], 0, 0xFF),
        iProduct=getVal(field["iProduct"], 0, 0xFF),
        iSerialNumber=getVal(field["iSerial"], 0, 0xFF),
        bNumConfigurations=getVal(field["bNumConfigurations"], 0,
                                  0xFF))


def parseConfiguration(field):
    """
    >>> f = {
    ... "name": "Configuration",
    ... "bLength":                 9,
    ... "bDescriptorType":         2,
    ... "wTotalLength":           53,
    ... "bNumInterfaces":          1,
    ... "bConfigurationValue":     1,
    ... "iConfiguration":          0,
    ... "bmAttributes":       "0x40",
    ... "bMaxPower":               0,
    ... "Interface": []}
    >>> c = parseConfiguration(f)
    >>> c.get()
    [9, 2, 53, 0, 1, 1, 0, 64, 0]
    """
    interface_list = [parse(i) for i in field["Interface"]]
    return ConfigDescriptor(
        bLength=getVal(field["bLength"], 0, 0xFF),
        bDescriptorType=getVal(
            field["bDescriptorType"], 2, 2),
        wTotalLength=getVal(
            field["wTotalLength"], 0, 0xFFFF),
        bNumInterfaces=getVal(
            field["bNumInterfaces"], 0, 0xFF),
        bConfigurationValue=getVal(
            field["bConfigurationValue"], 0, 0xFF),
        iConfiguration=getVal(
            field["iConfiguration"], 0, 0xFF),
        bmAttributes=getVal(
            field["bmAttributes"], 0, 0xFF),
        bMaxPower=getVal(field["bMaxPower"], 0, 0xFF),
        interfaces=interface_list)


class StringDescriptorDict(dict):
    '''Helper class to assign string descriptors to correct UsbDevice field'''


def parseStrings(field):
    """
    >>> f = {
    ... "name": "String",
    ... "bDescriptorType": 3,
    ... "0": ["0x0409"],
    ... "0x0409" : {
    ...     "1": "USB device"
    ...     }
    ... }
    >>> s = parseStrings(f)
    >>> s[0].get()
    [4, 3, 9, 4]
    >>> s[0x0409][1].get()
    [22, 3, 85, 0, 83, 0, 66, 0, 32, 0, 100, 0, 101, 0, 118, 0, 105, 0, 99, 0, 101, 0]
    """ # noqa
    descriptors = StringDescriptorDict()
    # At key 0 we expect an array of LangId codes
    langIdArray = [int(i, base=16) for i in field["0"]]
    descriptors[0] = StringDescriptorZero(langIdArray)
    for lid in field["0"]:
        descriptors[int(lid, base=16)] = {int(i, base=16):
                                          StringDescriptor(field[lid][i])
                                          for i in field[lid]}
    return descriptors


def parseEndpoint(e):
    """
    >>> f = {
    ... "name":                "Endpoint",
    ... "bLength":                      7,
    ... "bDescriptorType":              5,
    ... "bEndpointAddress":     [3, "IN"],
    ... "bmAttributes": {
    ...   "Transfer":              "Bulk",
    ...   "Synch":                 "None",
    ...   "Usage":                 "Data"
    ... },
    ... "wMaxPacketSize":        "0x0040",
    ... "bInterval":                    1
    ... }
    >>> e = parseEndpoint(f)
    >>> e.get()
    [7, 5, 131, 2, 64, 0, 1]

    >>> f = {
    ... "name":                "Endpoint",
    ... "bLength":                      7,
    ... "bDescriptorType":              5,
    ... "bEndpointAddress":        "0x81",
    ... "bmAttributes":            "0x82",
    ... "wMaxPacketSize":        "0x0040",
    ... "bInterval":                    1
    ... }
    >>> e = parseEndpoint(f)
    >>> e.get()
    [7, 5, 129, 130, 64, 0, 1]
    """
    bLength = getVal(e["bLength"], 0, 0xFF)

    if isinstance(e["bEndpointAddress"], str):
        bEndpointAddress = getVal(e["bEndpointAddress"], 0, 0xFF)
    else:
        if e["bEndpointAddress"][1] == "IN":
            endpointDir = EndpointDescriptor.Direction.IN
        elif e["bEndpointAddress"][1] == "OUT":
            endpointDir = EndpointDescriptor.Direction.OUT

        bEndpointAddress = getVal(e["bEndpointAddress"][0], 0,
                                  15) | (endpointDir << 7)

    if isinstance(e["bmAttributes"], str):
        bmAttributes = getVal(e["bmAttributes"], 0, 0xFF)
    else:
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
    wMaxPacketSize = getVal(e["wMaxPacketSize"], 0, 0x1FFF)
    bInterval = getVal(e["bInterval"], 0, 0xFF)

    return EndpointDescriptor(bLength, bEndpointAddress, bmAttributes,
                              wMaxPacketSize, bInterval)


def getClassParsers(c):
    parsers = {
            DFU_CLASS_CODE: dfuParsers,
            CDC.Type.COMM: cdcParsers
            }
    try:
        return parsers[c]
    except KeyError:
        return None


def parseInterface(intf):
    """
    >>> f = {
    ... "bLength":                 9,
    ... "bDescriptorType":         4,
    ... "bInterfaceNumber":        0,
    ... "bAlternateSetting":       0,
    ... "bNumEndpoints":           5,
    ... "bInterfaceClass":         5,
    ... "bInterfaceSubClass":      1,
    ... "bInterfaceProtocol":      2,
    ... "iInterface":              0,
    ... "Subdescriptors": []}
    >>> i = parseInterface(f)
    >>> i.get()
    [9, 4, 0, 0, 5, 5, 1, 2, 0]
    """
    bInterfaceClass = getVal(intf["bInterfaceClass"], 0, 0xFF)
    bInterfaceSubclass = getVal(intf["bInterfaceSubClass"], 0, 0xFF)
    bInterfaceProtocol = getVal(intf["bInterfaceProtocol"], 0, 0xFF)
    parsers = getClassParsers(bInterfaceClass)
    sub_list = [parse(e, parsers) for e in intf["Subdescriptors"]]
    return InterfaceDescriptor(
        bLength=getVal(intf["bLength"], 0, 0xFF),
        bInterfaceNumber=getVal(intf["bInterfaceNumber"], 0, 0xFF),
        bAlternateSetting=getVal(intf["bAlternateSetting"], 0, 0xFF),
        bNumEndpoints=getVal(intf["bNumEndpoints"], 0, 0xFF),
        bInterfaceClass=bInterfaceClass,
        bInterfaceSubclass=bInterfaceSubclass,
        bInterfaceProtocol=bInterfaceProtocol,
        iInterface=getVal(intf["iInterface"], 0, 0xFF),
        subdescriptors=sub_list)


def parseDeviceQualifier(field):
    """
    >>> f = {
    ... "name":   "Device Qualifier",
    ... "bLength":                18,
    ... "bDescriptorType":         1,
    ... "bcdUSB":           "0x0100",
    ... "bDeviceClass":          255,
    ... "bDeviceSubClass":         0,
    ... "bDeviceProtocol":       255,
    ... "bMaxPacketSize0":        64,
    ... "bNumConfigurations":      1
    ... }
    >>> dq = parseDeviceQualifier(f)
    >>> dq.get()
    [18, 1, 0, 1, 255, 0, 255, 64, 1, 0]
    """
    return DeviceQualifierDescriptor(
        bLength=getVal(field["bLength"], 0, 0xFF),
        bDescriptorType=getVal(field["bDescriptorType"], 0, 0xFF),
        bcdUSB=getVal(field["bcdUSB"], 0, 0xFFFF),
        bDeviceClass=getVal(field["bDeviceClass"], 0, 0xFF),
        bDeviceSubClass=getVal(field["bDeviceSubClass"], 0, 0xFF),
        bDeviceProtocol=getVal(field["bDeviceProtocol"], 0, 0xFF),
        bMaxPacketSize0=getVal(field["bMaxPacketSize0"], 0, 0xFF),
        bNumConfigurations=getVal(field["bNumConfigurations"], 0, 0xFF)
    )


def parseBOS(_):
    print("BOS descriptors are not supported")


standardParsers = {
                   Descriptor.Types.DEVICE: parseDevice,
                   Descriptor.Types.CONFIGURATION: parseConfiguration,
                   Descriptor.Types.STRING: parseStrings,
                   Descriptor.Types.INTERFACE: parseInterface,
                   Descriptor.Types.ENDPOINT: parseEndpoint,
                   Descriptor.Types.DEVICE_QUALIFIER: parseDeviceQualifier,
                   # TODO: Descriptor.Types.OTHER_SPEED_CONFIGURATION
                   # TODO: Descriptor.Types.INTERFACE_POWER
                   Descriptor.Types.BOS: parseBOS
                  }


def parse(field, customParsers=None):
    """
    >>> f = {
    ...  "name":      "Configuration",
    ...  "bLength":                 9,
    ...  "bDescriptorType":         2,
    ...  "wTotalLength":           53,
    ...  "bNumInterfaces":          1,
    ...  "bConfigurationValue":     1,
    ...  "iConfiguration":          0,
    ...  "bmAttributes":       "0x40",
    ...  "bMaxPower":               0,
    ...  "Interface": [
    ...    {
    ...      "bLength":                 9,
    ...      "bDescriptorType":         4,
    ...      "bInterfaceNumber":        0,
    ...      "bAlternateSetting":       0,
    ...      "bNumEndpoints":           5,
    ...      "bInterfaceClass":         5,
    ...      "bInterfaceSubClass":      1,
    ...      "bInterfaceProtocol":     55,
    ...      "iInterface":              0,
    ...      "Subdescriptors": [
    ...        {
    ...          "name":            "Endpoint",
    ...          "bLength":                  7,
    ...          "bDescriptorType":          5,
    ...          "bEndpointAddress": [1, "IN"],
    ...          "bmAttributes": {
    ...            "Transfer": "Isochronous",
    ...            "Synch": "None",
    ...            "Usage": "Data"
    ...          },
    ...          "wMaxPacketSize":    "0x0100",
    ...          "bInterval":                1
    ...        },
    ...        {
    ...          "name":            "Endpoint",
    ...          "bLength":                  7,
    ...          "bDescriptorType":          5,
    ...          "bEndpointAddress": [2, "OUT"],
    ...          "bmAttributes": {
    ...            "Transfer": "Isochronous",
    ...            "Synch": "None",
    ...            "Usage": "Data"
    ...          },
    ...          "wMaxPacketSize":   "0x0100",
    ...          "bInterval":               1
    ...        }
    ...      ]
    ...    }
    ...  ]
    ... }
    >>> c = parse(f)
    >>> c.get()
    [9, 2, 53, 0, 1, 1, 0, 64, 0, 9, 4, 0, 0, 5, 5, 1, 55, 0, 7, 5, 129, 1, 0, 1, 1, 7, 5, 2, 1, 0, 1, 1]
    """ # noqa
    bDescriptorType = getVal(field["bDescriptorType"], 0, 0xFF)
    if isStandard(bDescriptorType):
        return standardParsers[bDescriptorType](field)
    elif customParsers is not None:
        try:
            return customParsers[bDescriptorType](field)
        except KeyError:
            print("Unexpected descriptor type: {}, ignoring"
                  .format(bDescriptorType))
    else:
        print("Unknown descriptor: {}".format(bDescriptorType))
        return None


class UsbDevice:
    """Object for storing USB descriptors information in a structured manner

    Args:
        config_file (path): JSON file containing descriptor values.
    """
    def __init__(self, config_file):
        self.configDescriptor = {}
        self.descriptors = []  # Other descriptors
        with open(config_file, "r") as f:
            data = json.load(f)
            for item in data:
                desc = parse(item)
                if isinstance(desc, DeviceDescriptor):
                    self.deviceDescriptor = desc
                elif isinstance(desc, ConfigDescriptor):
                    self.configDescriptor[desc.bConfigurationValue] = desc
                elif isinstance(desc, StringDescriptorDict):
                    self.stringDescriptor = desc
                elif desc is not None:
                    self.descriptors.append(desc)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
