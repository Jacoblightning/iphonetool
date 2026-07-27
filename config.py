from enum import IntEnum

APPLE_VENDORID = 0x05AC
class AppleProductId(IntEnum):
    RECOVERY = 0x1281
    DFU      = 0x1227

USBLITER8_TRANSFER_SIZE = 0x800
