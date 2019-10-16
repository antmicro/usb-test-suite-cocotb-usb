class Descriptor():
    """Base class for storing common descriptor elements"""
    class LangId():
        UNSPECIFIED = 0x0000
        ENG = 0x0409

    class Types():
        DEVICE = 1
        CONFIGURATION = 2
        STRING = 3
        INTERFACE = 4
        ENDPOINT = 5
        DEVICE_QUALIFIER = 6
        OTHER_SPEED_CONFIGURATION = 7
        INTERFACE_POWER = 8

        # Class specific types
        CLASS_SPECIFIC_DEVICE = 0x21
        CLASS_SPECIFIC_CONFIGURATION = 0x22
        CLASS_SPECIFIC_STRING = 0x23
        CLASS_SPECIFIC_INTERFACE = 0x24
        CLASS_SPECIFIC_ENDPOINT = 0x25


class DeviceDescriptor(Descriptor):
    """Class representing USB device descriptor"""
    def __init__(self,
                 bLength,
                 bcdUSB,
                 bDeviceClass,
                 bDeviceSubClass,
                 bDeviceProtocol,
                 bMaxPacketSize0,
                 idVendor,
                 idProduct,
                 bcdDevice,
                 iManufacturer,
                 iProduct,
                 iSerialNumber,
                 bNumConfigurations,
                 bDescriptorType=Descriptor.Types.DEVICE):
        self.bLength = bLength
        self.bDescriptorType = bDescriptorType
        self.bcdUSB = bcdUSB
        self.bDeviceClass = bDeviceClass
        self.bDeviceSubClass = bDeviceSubClass
        self.bDeviceProtocol = bDeviceProtocol
        self.bMaxPacketSize0 = bMaxPacketSize0
        self.idVendor = idVendor
        self.idProduct = idProduct
        self.bcdDevice = bcdDevice
        self.iManufacturer = iManufacturer
        self.iProduct = iProduct
        self.iSerialNumber = iSerialNumber
        self.bNumConfigurations = bNumConfigurations

    def get(self):
        """Return descriptor contents as list of bytes"""
        return [
            self.bLength, self.bDescriptorType, self.bcdUSB & 0x00FF,
            self.bcdUSB >> 8, self.bDeviceClass, self.bDeviceSubClass,
            self.bDeviceProtocol, self.bMaxPacketSize0, self.idVendor & 0x00FF,
            self.idVendor >> 8, self.idProduct & 0x00FF, self.idProduct >> 8,
            self.bcdDevice & 0x00FF, self.bcdDevice >> 8, self.iManufacturer,
            self.iProduct, self.iSerialNumber, self.bNumConfigurations
        ]


class EndpointDescriptor(Descriptor):
    """Class representing standard USB endpoint descriptor"""
    class Direction:
        OUT = 0
        IN = 1

    class TransferType:
        CONTROL = 0
        ISOCHRONOUS = 1
        BULK = 2
        INTERRUPT = 3

    class SynchronizationType:
        NO = 0
        ASYNC = 1
        ADAPTIVE = 2
        SYNC = 3

    class UsageType:
        DATA = 0
        FEEDBACK = 1
        IFDATA = 2  # Implicit feedback Data endpoint
        # Reserved - 3

    def __init__(self,
                 bLength,
                 bEndpointAddress,
                 bmAttributes,
                 wMaxPacketSize,
                 bInterval,
                 bDescriptorType=Descriptor.Types.ENDPOINT):
        self.bLength = bLength
        self.bEndpointAddress = bEndpointAddress
        self.bmAttributes = bmAttributes
        self.wMaxPacketSize = wMaxPacketSize
        self.bInterval = bInterval
        self.bDescriptorType = bDescriptorType

    def get(self):
        """Return descriptor contents as list of bytes"""
        return [
            self.bLength, self.bDescriptorType, self.bEndpointAddress,
            self.bmAttributes, self.wMaxPacketSize & 0x00FF,
            self.wMaxPacketSize >> 8, self.bInterval
        ]


class InterfaceDescriptor(Descriptor):
    """Class representing standard USB interface descriptor"""
    def __init__(self,
                 bLength,
                 bInterfaceNumber,
                 bAlternateSetting,
                 bNumEndpoints,
                 bInterfaceClass,
                 bInterfaceSubclass,
                 bInterfaceProtocol,
                 iInterface,
                 bDescriptorType=Descriptor.Types.INTERFACE,
                 subdescriptors=[]):
        self.bLength = bLength
        self.bInterfaceNumber = bInterfaceNumber
        self.bAlternateSetting = bAlternateSetting
        self.bNumEndpoints = bNumEndpoints
        self.bInterfaceClass = bInterfaceClass
        self.bInterfaceSubclass = bInterfaceSubclass
        self.bInterfaceProtocol = bInterfaceProtocol
        self.iInterface = iInterface
        self.bDescriptorType = bDescriptorType
        self.subdescriptors = subdescriptors

    def get(self):
        """Return descriptor contents as list of bytes"""
        desc = [
            self.bLength, self.bDescriptorType, self.bInterfaceNumber,
            self.bAlternateSetting, self.bNumEndpoints, self.bInterfaceClass,
            self.bInterfaceSubclass, self.bInterfaceProtocol, self.iInterface
        ]
        desc += [b for e in self.subdescriptors for b in e.get()]
        return desc


class ConfigDescriptor(Descriptor):
    """Class representing standard USB configuration descriptor
    Can also represent OTHER_SPEED_CONFIGURATION descriptor, as they have
    identical contents.
    """
    class Attributes():
        NONE = 0
        BUS_POWERED = 1 << 7  # USB 1.0 only, otherwise reserved
        SELF_POWERED = 1 << 6
        REMOTE_WAKEUP = 1 << 5
        # Reserved 1<<4..0

    def __init__(self,
                 bLength,
                 wTotalLength,
                 bNumInterfaces,
                 bConfigurationValue,
                 iConfiguration,
                 bmAttributes,
                 bMaxPower,
                 bDescriptorType=Descriptor.Types.CONFIGURATION,
                 interfaces=[]):
        self.bLength = bLength
        self.wTotalLength = wTotalLength
        self.bNumInterfaces = bNumInterfaces
        self.bConfigurationValue = bConfigurationValue
        self.iConfiguration = iConfiguration
        self.bmAttributes = bmAttributes
        self.bMaxPower = bMaxPower
        self.bDescriptorType = bDescriptorType
        self.interfaces = interfaces

    def get(self):
        """Return descriptor contents as list of bytes"""
        desc = [
            self.bLength, self.bDescriptorType, self.wTotalLength & 0x00FF,
            self.wTotalLength >> 8, self.bNumInterfaces,
            self.bConfigurationValue, self.iConfiguration, self.bmAttributes,
            self.bMaxPower
        ]
        desc += [b for i in self.interfaces for b in i.get()]
        return desc


class StringDescriptorZero(Descriptor):
    """Class representing USB string descriptor with index 0.
     This one is different than other string descriptors in that it contains
     an array of supported LanguageIds instead of an actual string.
    """
    def __init__(self,
                 wLangIdList,
                 bLength=None,
                 bDescriptorType=Descriptor.Types.STRING):
        self.wLangId = wLangIdList
        self.bLength = bLength
        self.bDescriptorType = bDescriptorType

    def get(self):
        """Return descriptor contents as list of bytes"""
        descriptor = []
        for i in self.wLangId:
            descriptor.append(i & 0x00FF)
            descriptor.append(i >> 8)
        descriptor.insert(0, self.bDescriptorType)
        if self.bLength is None:
            bLength = 1 + len(descriptor)
        else:
            bLength = self.bLength
        descriptor.insert(0, bLength)
        return descriptor


class StringDescriptor(Descriptor):
    """Class representing standard USB string descriptor"""
    def __init__(self,
                 bString,
                 bLength=None,
                 bDescriptorType=Descriptor.Types.STRING):
        self.bString = bString
        self.bLength = bLength
        self.bDescriptorType = bDescriptorType

    def get(self):
        """Return descriptor contents as list of bytes"""
        descriptor = []
        for c in self.bString:
            descriptor.append(ord(c) & 0x00FF)
            descriptor.append(ord(c) >> 8)
        descriptor.insert(0, self.bDescriptorType)
        if self.bLength is None:
            bLength = 1 + len(descriptor)
        else:
            bLength = self.bLength
        descriptor.insert(0, bLength)
        return descriptor


class DeviceQualifierDescriptor(Descriptor):
    """Class representing standard USB device qualifier descriptor"""
    def __init__(self,
                 bcdUSB,
                 bDeviceClass,
                 bDeviceSubClass,
                 bDeviceProtocol,
                 bMaxPacketSize0,
                 bNumConfigurations,
                 bLength=10,
                 bDescriptorType=Descriptor.Types.DEVICE_QUALIFIER):
        self.bcdUSB = bcdUSB
        self.bDeviceClass = bDeviceClass
        self.bDeviceSubClass = bDeviceSubClass
        self.bDeviceProtocol = bDeviceProtocol
        self.bMaxPacketSize0 = bMaxPacketSize0
        self.bNumConfigurations = bNumConfigurations
        self.bLength = bLength
        self.bDescriptorType = bDescriptorType

    def get(self):
        """Return descriptor contents as list of bytes"""
        return [
            self.bLength, self.bDescriptorType, self.bcdUSB & 0x00FF,
            self.bcdUSB >> 8, self.bDeviceClass, self.bDeviceSubClass,
            self.bDeviceProtocol, self.bMaxPacketSize0,
            self.bNumConfigurations, 0x00
        ]  # Reserved for future use


class FeatureSelector:
    ENDPOINT_HALT = 0
    DEVICE_REMOTE_WAKEUP = 1
    TEST_MODE = 2

    class TestMode:
        # Reserved 0x00
        TEST_J = 0x01
        TEST_K = 0x02
        TEST_SE0_NAK = 0x03
        TEST_PACKET = 0x04
        TEST_FORCE_ENABLE = 0x05
        # Reserved 0x06-0xFF


class USBDeviceRequest():
    """Class grouping common USB request definitions"""
    class Type():
        # Format constants from USB Spec 9.3
        # Direction
        HOST_TO_DEVICE = 0 << 7
        DEVICE_TO_HOST = 1 << 7
        # Type
        STANDARD = 0 << 5
        CLASS = 1 << 5
        VENDOR = 2 << 5
        RESERVED = 3 << 5
        # Recipient
        DEVICE = 0
        INTERFACE = 1
        ENDPOINT = 2
        OTHER = 3

    class Code():
        GET_STATUS = 0
        CLEAR_FEATURE = 1
        # Reserved for future use = 2
        SET_FEATURE = 3
        # Reserved for future use = 4
        SET_ADDRESS = 5
        GET_DESCRIPTOR = 6
        SET_DESCRIPTOR = 7
        GET_CONFIGURATION = 8
        SET_CONFIGURATION = 9
        GET_INTERFACE = 10
        SET_INTERFACE = 11
        SYNCH_FRAME = 12

    def build(bmRequestType, bRequest, wValue, wIndex, wLength):
        """Create a USB request with provided values"""
        return [
            bmRequestType,
            bRequest,
            wValue & 0x00FF,
            wValue >> 8,
            wIndex & 0x00FF,
            wIndex >> 8,
            wLength & 0x00FF,
            wLength >> 8,
        ]


def setAddressRequest(address):
    """Create a standard SET_ADDRESS USB request

    Args:
        address (int): Address to be set. Should be below 128.
    """
    assert address <= 127
    return USBDeviceRequest.build(USBDeviceRequest.Type.HOST_TO_DEVICE
                                  | USBDeviceRequest.Type.STANDARD
                                  | USBDeviceRequest.Type.DEVICE,
                                  bRequest=USBDeviceRequest.Code.SET_ADDRESS,
                                  wValue=address,
                                  wIndex=0,
                                  wLength=0)


def getDescriptorRequest(descriptor_type, descriptor_index, lang_id, length):
    """Create a standard GET_DESCRIPTOR USB request

    Args:
        descriptor_type: Type of the descriptor as per USB specification.
        descriptor_index: Index of descriptor to be read.
        lang_id (int): LangId of descriptor to be read or 0 if unspecified.
        length (int): Number of bytes requested.
    """
    return USBDeviceRequest.build(
        USBDeviceRequest.Type.DEVICE_TO_HOST | USBDeviceRequest.Type.STANDARD
        | USBDeviceRequest.Type.DEVICE,
        bRequest=USBDeviceRequest.Code.GET_DESCRIPTOR,
        wValue=descriptor_type << 8 | descriptor_index,
        wIndex=lang_id,
        wLength=length)


def setConfigurationRequest(configuration):
    """Create a standard SET_CONFIGURATION USB request

    Args:
        configuration (int): Configuration value to be set.
            Should be below 256.
    """
    # Upper byte of wValue byte is reserved here
    assert configuration <= 255
    return USBDeviceRequest.build(
        USBDeviceRequest.Type.HOST_TO_DEVICE | USBDeviceRequest.Type.STANDARD
        | USBDeviceRequest.Type.DEVICE,
        bRequest=USBDeviceRequest.Code.SET_CONFIGURATION,
        wValue=configuration,
        wIndex=0,
        wLength=0)


def setFeatureRequest(feature_selector, recipient, target=0, test_selector=0):
    return USBDeviceRequest.build(USBDeviceRequest.Type.HOST_TO_DEVICE
                                  | USBDeviceRequest.Type.STANDARD | recipient,
                                  bRequest=USBDeviceRequest.Code.SET_FEATURE,
                                  wValue=feature_selector << 8
                                  | feature_selector,
                                  wIndex=test_selector << 8 | target,
                                  wLength=0)
