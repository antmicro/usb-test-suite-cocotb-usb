class Descriptor():
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

class DeviceDescriptor(Descriptor):
    def build(bLength, bcdUSB, bDeviceClass,
            bDeviceSubClass, bDeviceProtocol, bMaxPacketSize0, idVendor, idProduct, bcdDevice,
            iManufacturer, iProduct, iSerialNumber, bNumConfigurations, bDescriptorType=Descriptor.Types.DEVICE):
        return [bLength,
                bDescriptorType,
                bcdUSB >> 8,
                bcdUSB & 0x00FF,
                bDeviceClass,
                bDeviceSubClass,
                bDeviceProtocol,
                bMaxPacketSize0,
                idVendor >> 8,
                idVendor & 0x00FF,
                idProduct >> 8, idProduct & 0x00FF,
                bcdDevice >> 8,
                bcdDevice & 0x00FF,
                iManufacturer,
                iProduct,
                iSerialNumber,
                bNumConfigurations]

class ConfigDescriptor(Descriptor):
    class Attributes():
        NONE = 0
        SELF_POWERED = 1<<6
        REMOTE_WAKEUP = 1<<5
        # Reserved 1<<4..0

    def build(bLength,
            wTotalLength,
            bNumInterfaces,
            bConfigurationValue,
            iConfiguration,
            bmAttributes,
            bMaxPower,
            bDescriptorType = Descriptor.Types.CONFIGURATION):
        return [bLength,
                bDescriptorType,
                wTotalLength >> 8,
                wTotalLength & 0x00FF,
                bNumInterfaces,
                bConfigurationValue,
                iConfiguration,
                # 1<<7 must be set to 1 for historical reasons
                1<<7 | bmAttributes,
                bMaxPower] #TODO: Allow returning all related interface and endpoint descriptors

class StringDescriptor(Descriptor):
    def buildIdx0(wLangIdList,
            bLength = None,
            bDescriptorType = Descriptor.Types.STRING
            ):
        descriptor = []
        for i in wLangIdList:
            descriptor.append(i >> 8)
            descriptor.append(i & 0x00FF)
        descriptor.insert(0, bDescriptorType)
        if bLength == None:
            bLength = 1 + len(descriptor)
        descriptor.insert(0, bLength)
        return descriptor

    def build(bString,
            bLength = None,
            bDescriptorType = Descriptor.Types.STRING
            ):
        descriptor = []
        for c in bString:
            descriptor.append(ord(c) >> 8)
            descriptor.append(ord(c) & 0x00FF)
        descriptor.insert(0, bDescriptorType)
        if bLength == None:
            bLength = 1 + len(descriptor)
        descriptor.insert(0, bLength)
        return descriptor

class RequestType():
    # Format constants from USB Spec 9.3
    # Direction
    HOST_TO_DEVICE = 0<<7
    DEVICE_TO_HOST = 1<<7
    # Type
    STANDARD = 0<<5
    CLASS = 1<<5
    VENDOR = 2<<5
    RESERVED = 3<<5
    # Recipient
    DEVICE = 0
    INTERFACE = 1
    ENDPOINT = 2
    OTHER = 3

class RequestCodes():
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

class USBDeviceRequest():
    class Type():
        # Format constants from USB Spec 9.3
        # Direction
        HOST_TO_DEVICE = 0<<7
        DEVICE_TO_HOST = 1<<7
        # Type
        STANDARD = 0<<5
        CLASS = 1<<5
        VENDOR = 2<<5
        RESERVED = 3<<5
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
        return [bmRequestType,
                bRequest,
                wValue >> 8,
                wValue & 0x00FF,
                wIndex >> 8,
                wIndex & 0x00FF,
                wLength >> 8,
                wLength & 0x00FF,
                ]

def setAddressRequest(address):
    assert address <= 127
    return USBDeviceRequest.build(USBDeviceRequest.Type.HOST_TO_DEVICE | USBDeviceRequest.Type.STANDARD | USBDeviceRequest.Type.DEVICE,
            bRequest = USBDeviceRequest.Code.SET_ADDRESS,
            wValue = address,
            wIndex = 0,
            wLength = 0)

def getDescriptorRequest(descriptor_type, descriptor_index, lang_id, length):
    return USBDeviceRequest.build(USBDeviceRequest.Type.DEVICE_TO_HOST | USBDeviceRequest.Type.STANDARD | USBDeviceRequest.Type.DEVICE,
            bRequest = USBDeviceRequest.Code.GET_DESCRIPTOR,
            wValue = descriptor_type << 8 | descriptor_index,
            wIndex = lang_id,
            wLength = length)

def setConfigurationRequest(configuration):
    # Upper byte of wValue byte is reserved here
    assert configuration <= 255
    return USBDeviceRequest.build(USBDeviceRequest.Type.HOST_TO_DEVICE | USBDeviceRequest.Type.STANDARD | USBDeviceRequest.Type.DEVICE,
            bRequest = USBDeviceRequest.Code.SET_CONFIGURATION,
            wValue = configuration,
            wIndex = 0,
            wLength = 0)

