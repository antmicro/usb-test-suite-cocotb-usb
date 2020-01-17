from cocotb_usb.usb.pid import PID


class DotDict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def bitstr_to_num(bitstr):
    if not bitstr:
        return 0
    l = list(bitstr)
    l.reverse()
    return int(''.join(l), 2)


def get_category(pidname):
    if pidname in ('OUT', 'IN', 'SOF', 'SETUP'):
        return 'TOKEN'
    elif pidname in ('DATA0', 'DATA1', 'DATA2', 'MDATA'):
        return 'DATA'
    elif pidname in ('ACK', 'NAK', 'STALL', 'NYET'):
        return 'HANDSHAKE'
    else:
        return 'SPECIAL'


def decode_packet(packet):
    """
    Decodes single packet in the format as passed to _host_send_packet() method.
    Packet is a 'str' of '0' and '1', without SYNC field.
    """
    # use dictionary, as depending on PID we will have different fields
    decoded = DotDict()

    # decoding based on Sigrok usb_packet decoder
    pid = packet[:8]  # just PID bits
    pid = PID(int(pid[:4][::-1], 2))  # convert to int, then to PID
    decoded.pid = pid

    # add dummy SYNC bits to packet so that idicies are consistent with real ones
    packet = (8 * '0') + packet

    if pid in (PID.OUT, PID.IN, PID.SOF, PID.SETUP, PID.PING):
        if pid == PID.SOF:
            # Bits[16:26]: Framenum
            decoded.framenum = bitstr_to_num(packet[16:26 + 1])
        else:
            # Bits[16:22]: Addr
            decoded.addr = bitstr_to_num(packet[16:22 + 1])
            # Bits[23:26]: EP
            decoded.endp = bitstr_to_num(packet[23:26 + 1])
        # Bits[27:31]: CRC5
        decoded.crc5 = bitstr_to_num(packet[27:31 + 1])

    elif pid in (PID.DATA0, PID.DATA1, PID.DATA2, PID.MDATA):
        # Bits[16:packetlen-16]: Data
        data = packet[16:-16]
        assert len(data) % 8 == 0, 'len(data) (= %d) must be a multiple of 8.' % (len(data))

        databytes = []
        for i in range(0, len(data), 8):
            db = bitstr_to_num(data[i:i + 8])
            databytes.append(db)

        decoded.data = databytes
        decoded.data_bits = data  # for convenience

        # Bits[packetlen-16:packetlen]: CRC16
        decoded.crc16 = bitstr_to_num(packet[-16:])

    # nothing to do with other packets
    # just assign PID category
    decoded.category = get_category(decoded.pid.name)

    return decoded
