
import usb.core
import asyncio

import argparse
import subprocess

import normal

from typing import Optional
from collections.abc import Callable

import helpers

try:
    import pymobiledevice3
except ImportError:
    print("pymobiledevice3 not installed and is needed for normal/recovery mode operation. Please install pymobiledevice3")
    raise

async def print_in(secs: float, message: str) -> None:
    try:
        await asyncio.sleep(secs)
        print(message)
    except asyncio.CancelledError:
        pass

async def main(dev: usb.core.Device, parser: argparse.ArgumentParser, subparsers: argparse._SubParsersAction):
    subparsers.add_parser("dfu_helper", help="Help put device into DFU mode")
    subparsers.add_parser("exit_recovery", help="Exit recovery mode")

    args = parser.parse_args()

    return await main_real(dev, args.action)

# This can be called easily from other python files
async def main_real(dev: usb.core.Device, action: str) -> int:
    try:
        serial = dev.serial_number
    except ValueError as e:
        raise ValueError("This script must be run as root for iPhones in recovery or dfu mode.") from e
    ecid = int(helpers.serial_info(serial, "ECID"), 16)

    irecovery = subprocess.check_output(["irecovery", "-q", "-i", hex(ecid)]).decode()

    match action:
        case "info":
            print(f"Detected recovery mode {helpers.irecovery_info(irecovery, "NAME")}:")
            print("iPhone ID:", ecid)
            print("iPhone internal version:", helpers.irecovery_info(irecovery, "PRODUCT"))
            print("Codename:", helpers.irecovery_info(irecovery, "MODEL"))
            print("CPU:", helpers.serial_info(serial, "CPID"))
        case "exit_recovery":
            print(f"Telling device {ecid} to exit recovery.", flush=True)
            helpers.irecovery_command("setenv auto-boot true", ecid)
            helpers.irecovery_command("saveenv", ecid)
            helpers.irecovery_command("reboot", ecid)
            print(f"Device {ecid} has exited recovery", flush=True)
        case "dfu_helper":
            helpers.irecovery_command("setenv auto-boot true", ecid)
            helpers.irecovery_command("saveenv", ecid)

            input("Hold down buttons 1 & 2 on the device (and keep holding until this program says stop) and press enter.")

            helpers.irecovery_command("reset", ecid)

            await asyncio.sleep(2.5)

            print("Release button 1. Keep holding button 2")

            info_task = asyncio.create_task(print_in(8, "Whoops. Device did not enter DFU mode. Waiting for re-connect."))
            dev = await helpers.wait_device()
            canceled = info_task.cancel()

            # Now actually check if the device entered DFU
            mode = helpers.classify_mode(dev)

            match mode:
                case helpers.DeviceMode.NORMAL:
                    if not canceled:
                        # Print the message now if it wasn't printed before
                        print("Whoops. Device did not enter DFU mode.")
                    print("Device re-connected in normal mode.")
                    return await normal.main_real(dev, "dfu_helper")
                case helpers.DeviceMode.RECOVERY:
                    if not canceled:
                        # Print the message now if it wasn't printed before
                        print("Whoops. Device did not enter DFU mode.")
                    print("Device re-connected in recovery mode.")
                    return await main_real(dev, "dfu_helper")
                case helpers.DeviceMode.DFU:
                    print("Device entered DFU mode successfully!")

    return 0
