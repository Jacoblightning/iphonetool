#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pymobiledevice3>=10.1.0",
#     "pyusb>=1.3.1",
# ]
# ///

try:
    import usb.core
except ImportError:
    print("pyusb not installed and is needed for all operations. Please install pyusb")
    raise
import argparse
import asyncio
import sys
from enum import IntEnum

from . import dfu, helpers, normal, recovery


async def main() -> int:
    if "-w" in sys.argv or "--wait" in sys.argv:
        print("Waiting for device...")
        dev = await helpers.wait_device()
        print("Found device")
    else:
        dev = helpers.get_device()

    # If this fails, it will fall through to a "normal" device below
    if dev is None and ("-h" not in sys.argv and "--help" not in sys.argv):
        print("No idevice found :(")
        return 1

    parser = argparse.ArgumentParser()
    # This is only for showing up in help
    parser.add_argument(
        "-w", "--wait", help="Wait for a device to appear", action="store_true"
    )

    if dev is None:
        return await normal.main(None, parser)

    # Figure out what mode the device is in
    match helpers.classify_mode(dev):
        case helpers.DeviceMode.NORMAL:
            return await normal.main(dev, parser)
        case helpers.DeviceMode.RECOVERY:
            return await recovery.main(dev, parser)
        case helpers.DeviceMode.DFU:
            return await dfu.main(dev, parser)

def runmain() -> int:
    return asyncio.run(main())

if __name__ == "__main__":
    exit(runmain())
