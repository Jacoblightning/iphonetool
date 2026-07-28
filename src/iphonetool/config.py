from enum import IntEnum

APPLE_VENDORID = 0x05AC


class AppleProductId(IntEnum):
    RECOVERY = 0x1281 # Technically there are 2 other recovery device ids but, as they are not recognized by the kernel, we're going to ignore them here: https://theapplewiki.com/wiki/Recovery_Mode_(Protocols) http://www.linux-usb.org/usb.ids
    DFU = 0x1227


USBLITER8_TRANSFER_SIZE = 0x800
