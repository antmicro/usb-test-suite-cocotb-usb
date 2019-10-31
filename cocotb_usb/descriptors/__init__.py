from struct import pack


class Descriptor:
    """Base class for storing common descriptor elements."""
    class LangId:
        UNSPECIFIED = 0x0000
        ENG = 0x0409

    class Types:
        DEVICE = 1
        CONFIGURATION = 2
        STRING = 3
        INTERFACE = 4
        ENDPOINT = 5
        DEVICE_QUALIFIER = 6
        OTHER_SPEED_CONFIGURATION = 7
        INTERFACE_POWER = 8
        BOS = 0x0F  # Added in USB 3.0 and 2.0 LPM

        # Class specific types
        CLASS_SPECIFIC_DEVICE = 0x21
        CLASS_SPECIFIC_CONFIGURATION = 0x22
        CLASS_SPECIFIC_STRING = 0x23
        CLASS_SPECIFIC_INTERFACE = 0x24
        CLASS_SPECIFIC_ENDPOINT = 0x25

    def get(self):
        """Return descriptor contents as a list of bytes."""
        return list(bytes(self))


class DeviceDescriptor(Descriptor):
    """Class representing USB device descriptor."""

    FORMAT = "<BBH4B3H4B"

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

    def __bytes__(self):
        """
        >>> d = DeviceDescriptor(
        ... bLength=0x0A,
        ... bcdUSB=0x0100,
        ... bDeviceClass=0xFF,
        ... bDeviceSubClass=0x00,
        ... bDeviceProtocol=0xAB,
        ... bMaxPacketSize0=64,
        ... idVendor=0x1234,
        ... idProduct=0x5678,
        ... bcdDevice=0x0502,
        ... iManufacturer=0x01,
        ... iProduct=0x02,
        ... iSerialNumber=0x03,
        ... bNumConfigurations=1)
        >>> bytes(d)
        b'\\n\\x01\\x00\\x01\\xff\\x00\\xab@4\\x12xV\\x02\\x05\\x01\\x02\\x03\\x01'
        """
        return pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.bcdUSB,
                    self.bDeviceClass,
                    self.bDeviceSubClass,
                    self.bDeviceProtocol,
                    self.bMaxPacketSize0,
                    self.idVendor,
                    self.idProduct,
                    self.bcdDevice,
                    self.iManufacturer,
                    self.iProduct,
                    self.iSerialNumber,
                    self.bNumConfigurations)


class EndpointDescriptor(Descriptor):
    """Class representing standard USB endpoint descriptor."""

    FORMAT = "<4BHB"

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

    def __bytes__(self):
        """
        >>> e = EndpointDescriptor(
        ... bLength=7,
        ... bEndpointAddress=0x82,
        ... bmAttributes=0x01,
        ... wMaxPacketSize=0x0100,
        ... bInterval=0x01)
        >>> bytes(e)
        b'\\x07\\x05\\x82\\x01\\x00\\x01\\x01'
        >>> e.get()
        [7, 5, 130, 1, 0, 1, 1]
        """
        return pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.bEndpointAddress,
                    self.bmAttributes,
                    self.wMaxPacketSize,
                    self.bInterval)


class InterfaceDescriptor(Descriptor):
    """Class representing standard USB interface descriptor."""

    FORMAT = "<BB7B"

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

    def __bytes__(self):
        """
        >>> i = InterfaceDescriptor(
        ... bLength=9,
        ... bInterfaceNumber=0,
        ... bAlternateSetting=0,
        ... bNumEndpoints=0,
        ... bInterfaceClass=0xFF,
        ... bInterfaceSubclass=0x01,
        ... bInterfaceProtocol=0xFF,
        ... iInterface=0)
        >>> bytes(i)
        b'\\t\\x04\\x00\\x00\\x00\\xff\\x01\\xff\\x00'
        >>> i.get()
        [9, 4, 0, 0, 0, 255, 1, 255, 0]

        >>> e = EndpointDescriptor(
        ... bLength=7,
        ... bEndpointAddress=0x82,
        ... bmAttributes=0x01,
        ... wMaxPacketSize=0x0100,
        ... bInterval=0x01)
        >>> i.subdescriptors = [e]
        >>> bytes(i)
        b'\\t\\x04\\x00\\x00\\x00\\xff\\x01\\xff\\x00\\x07\\x05\\x82\\x01\\x00\\x01\\x01'
        >>> i.get()
        [9, 4, 0, 0, 0, 255, 1, 255, 0, 7, 5, 130, 1, 0, 1, 1]
        """
        desc = pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.bInterfaceNumber,
                    self.bAlternateSetting,
                    self.bNumEndpoints,
                    self.bInterfaceClass,
                    self.bInterfaceSubclass,
                    self.bInterfaceProtocol,
                    self.iInterface)
        subdesc = b''.join([bytes(e) for e in self.subdescriptors])
        return b''.join([desc, subdesc])


class ConfigDescriptor(Descriptor):
    """Class representing standard USB configuration descriptor.

    Can also represent OTHER_SPEED_CONFIGURATION descriptor, as they have
    identical contents.
    """

    FORMAT = "<BBH5B"

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

    def __bytes__(self):
        """
        >>> c = ConfigDescriptor(
        ... bLength=9,
        ... wTotalLength=0x53,
        ... bNumInterfaces=1,
        ... bConfigurationValue=1,
        ... iConfiguration=0,
        ... bmAttributes=0x40,
        ... bMaxPower=0)
        >>> bytes(c)
        b'\\t\\x02S\\x00\\x01\\x01\\x00@\\x00'
        >>> c.get()
        [9, 2, 83, 0, 1, 1, 0, 64, 0]

        >>> e = EndpointDescriptor(
        ... bLength=7,
        ... bEndpointAddress=0x82,
        ... bmAttributes=0x01,
        ... wMaxPacketSize=0x0100,
        ... bInterval=0x01)
        >>> i = InterfaceDescriptor(
        ... bLength=9,
        ... bInterfaceNumber=0,
        ... bAlternateSetting=0,
        ... bNumEndpoints=0,
        ... bInterfaceClass=0xFF,
        ... bInterfaceSubclass=0x01,
        ... bInterfaceProtocol=0xFF,
        ... iInterface=0,
        ... subdescriptors=[e])
        >>> c.interfaces=[i]
        >>> bytes(c)
        b'\\t\\x02S\\x00\\x01\\x01\\x00@\\x00\\t\\x04\\x00\\x00\\x00\\xff\\x01\\xff\\x00\\x07\\x05\\x82\\x01\\x00\\x01\\x01'
        >>> c.get()
        [9, 2, 83, 0, 1, 1, 0, 64, 0, 9, 4, 0, 0, 0, 255, 1, 255, 0, 7, 5, 130, 1, 0, 1, 1]
        """ # noqa
        desc = pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.wTotalLength,
                    self.bNumInterfaces,
                    self.bConfigurationValue,
                    self.iConfiguration,
                    self.bmAttributes,
                    self.bMaxPower)
        subdesc = b''.join([bytes(i) for i in self.interfaces])
        return b''.join([desc, subdesc])


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
        if bLength is None:
            self.bLength = 2 + 2*len(wLangIdList)
        else:
            self.bLength = bLength
        self.bDescriptorType = bDescriptorType

    def __bytes__(self):
        """
        >>> s0 = StringDescriptorZero(wLangIdList=[0x0409])
        >>> bytes(s0)
        b'\\x04\\x03\\t\\x04'
        >>> s0.get()
        [4, 3, 9, 4]

        >>> s0 = StringDescriptorZero(wLangIdList=[0x0409, 0x0804, 0x0439, 0x040a])
        >>> bytes(s0)
        b'\\n\\x03\\t\\x04\\x04\\x089\\x04\\n\\x04'
        >>> s0.get()
        [10, 3, 9, 4, 4, 8, 57, 4, 10, 4]
        """ # noqa
        desc = pack("<BB{}H".format(len(self.wLangId)),
                    self.bLength,
                    self.bDescriptorType,
                    *self.wLangId)
        return desc


class StringDescriptor(Descriptor):
    """Class representing standard USB string descriptor."""
    def __init__(self,
                 bString,
                 bLength=None,
                 bDescriptorType=Descriptor.Types.STRING):
        self.bString = bString
        if bLength is None:
            self.bLength = 2 + 2*len(bString)
        else:
            self.bLength = bLength
        self.bDescriptorType = bDescriptorType

    def __bytes__(self):
        """
        >>> s1 = StringDescriptor("Product name")
        >>> bytes(s1)
        b'\\x1a\\x03P\\x00r\\x00o\\x00d\\x00u\\x00c\\x00t\\x00 \\x00n\\x00a\\x00m\\x00e\\x00'
        >>> s1.get()
        [26, 3, 80, 0, 114, 0, 111, 0, 100, 0, 117, 0, 99, 0, 116, 0, 32, 0, 110, 0, 97, 0, 109, 0, 101, 0]
        """ # noqa
        header = pack("<BB",
                      self.bLength,
                      self.bDescriptorType)
        desc = header + self.bString.encode("utf-16-le")
        return desc


class DeviceQualifierDescriptor(Descriptor):
    """Class representing standard USB device qualifier descriptor."""

    FORMAT = "<BBH6B"

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

    def __bytes__(self):
        """
        >>> d = DeviceQualifierDescriptor(
        ... bcdUSB=0x0100,
        ... bDeviceClass=0xFF,
        ... bDeviceSubClass=0x00,
        ... bDeviceProtocol=0xEE,
        ... bMaxPacketSize0=64,
        ... bNumConfigurations=1)
        >>> bytes(d)
        b'\\n\\x06\\x00\\x01\\xff\\x00\\xee@\\x01\\x00'
        >>> d.get()
        [10, 6, 0, 1, 255, 0, 238, 64, 1, 0]
        """
        return pack(self.FORMAT,
                    self.bLength,
                    self.bDescriptorType,
                    self.bcdUSB,
                    self.bDeviceClass,
                    self.bDeviceSubClass,
                    self.bDeviceProtocol,
                    self.bMaxPacketSize0,
                    self.bNumConfigurations,
                    0x00)  # Reserved for future use


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
    """Class grouping common USB request definitions."""

    FORMAT = "<BB3H"

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

    def __init__(self,
                 bmRequestType,
                 bRequest,
                 wValue,
                 wIndex,
                 wLength,
                 data=None):
        self.bmRequestType = bmRequestType
        self.bRequest = bRequest
        self.wValue = wValue
        self.wIndex = wIndex
        self.wLength = wLength

    def build(bmRequestType, bRequest, wValue, wIndex, wLength):
        """Create a USB request with provided values.

        .. doctest::

            >>> USBDeviceRequest.build(
            ... bmRequestType=0x00,
            ... bRequest=0x05,
            ... wValue=0x02,
            ... wIndex=0x00,
            ... wLength=0x00)
            [0, 5, 2, 0, 0, 0, 0, 0]
        """
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

    def __bytes__(self):
        """
        >>> r = USBDeviceRequest(
        ... bmRequestType=0x00,
        ... bRequest=0x05,
        ... wValue=0x02,
        ... wIndex=0x00,
        ... wLength=0x00)
        >>> bytes(r)
        b'\\x00\\x05\\x02\\x00\\x00\\x00\\x00\\x00'
        """
        return pack(self.FORMAT,
                    self.bmRequestType,
                    self.bRequest,
                    self.wValue,
                    self.wIndex,
                    self.wLength)


def setAddressRequest(address):
    """Create a standard SET_ADDRESS USB request.

    Args:
        address (int): Address to be set. Should be below 128.

    .. doctest::

        >>> setAddressRequest(0x30)
        [0, 5, 48, 0, 0, 0, 0, 0]
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
    """Create a standard GET_DESCRIPTOR USB request.

    Args:
        descriptor_type (int): Type of the descriptor as per
            USB specification.
        descriptor_index (int): Index of descriptor to be read.
        lang_id (int): LangId of descriptor to be read or 0 if unspecified.
        length (int): Number of bytes requested.

    .. doctest::

        >>> getDescriptorRequest(
        ... descriptor_type=2,
        ... descriptor_index=1,
        ... lang_id=0,
        ... length=9
        ... )
        [128, 6, 1, 2, 0, 0, 9, 0]
    """
    return USBDeviceRequest.build(
        USBDeviceRequest.Type.DEVICE_TO_HOST | USBDeviceRequest.Type.STANDARD
        | USBDeviceRequest.Type.DEVICE,
        bRequest=USBDeviceRequest.Code.GET_DESCRIPTOR,
        wValue=descriptor_type << 8 | descriptor_index,
        wIndex=lang_id,
        wLength=length)


def setConfigurationRequest(configuration):
    """Create a standard SET_CONFIGURATION USB request.

    Args:
        configuration (int): Configuration value to be set.
            Should be below 256.

    .. doctest::

         >>> setConfigurationRequest(3)
         [0, 9, 3, 0, 0, 0, 0, 0]
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
    """Create a standard SET_FEATURE USB request.

    Args:
        feature_selector (int): Feature selector as defined
            in USB specification.
        recipient (int): One of Device (0), Interface (1) or Endpoint (2).
        target (int): Number of interface or endpoint.
        test_selector (int): Test mode selector, valid only for TEST_MODE
            feature selector.

    .. doctest::

        >>> setFeatureRequest(
        ... feature_selector=0,
        ... recipient=0)
        [0, 3, 0, 0, 0, 0, 0, 0]
    """
    return USBDeviceRequest.build(USBDeviceRequest.Type.HOST_TO_DEVICE
                                  | USBDeviceRequest.Type.STANDARD | recipient,
                                  bRequest=USBDeviceRequest.Code.SET_FEATURE,
                                  wValue=feature_selector << 8
                                  | feature_selector,
                                  wIndex=test_selector << 8 | target,
                                  wLength=0)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
