import json
from .descriptors import (Descriptor, EndpointDescriptor,
                          InterfaceDescriptor,
                          ConfigDescriptor, DeviceDescriptor,
                          StringDescriptorZero, StringDescriptor,
                          DeviceQualifierDescriptor)
from .descriptors.dfu import DfuFunctionalDescriptor, DFU_CLASS_CODE


def getVal(val, minimum, maximum):
    '''Helper function to get values in given range'''
    if isinstance(val, str):
        val = int(val, base=16)
    if not minimum <= val <= maximum:
        raise ValueError()
    return val


def isStandard(descriptorType):
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


def parseDevice(field):
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
    bLength = getVal(e["bLength"], 0, 0xFF)

    if isinstance(e["bEndpointAddress"], str):
        bmAttributes = getVal(e["bEndpointAddress"], 0, 0xFF)
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
            DFU_CLASS_CODE: dfuParsers
            }
    try:
        return parsers[c]
    except KeyError:
        print("No parsers found for class {}".format(c))
        return None


def parseInterface(intf):
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
    '''Object for storing USB descriptors information in a structured manner'''
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
