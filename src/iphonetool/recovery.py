import argparse
import asyncio
import subprocess
from collections.abc import Callable
from typing import Optional

import usb.core

try:
    from . import helpers, normal
except ImportError:
    try:
        import helpers  # type: ignore
        import normal  # type: ignore
    except ImportError:
        try:
            from iphonetool import helpers, normal
        except ImportError:
            raise ImportError("Could not import needed modules")

try:
    import pymobiledevice3
except ImportError:
    print(
        "pymobiledevice3 not installed and is needed for normal/recovery mode operation. Please install pymobiledevice3"
    )
    raise


async def print_in(secs: float, message: str) -> None:
    try:
        await asyncio.sleep(secs)
        print(message)
    except asyncio.CancelledError:
        pass


async def func_info(dev: usb.core.Device, irecovery: str) -> int:
    print(f"Detected recovery mode {helpers.irecovery_info(irecovery, "NAME")}:")
    print("iPhone ID:", helpers.irecovery_info(irecovery, "ECID"))
    print("iPhone internal version:", helpers.irecovery_info(irecovery, "PRODUCT"))
    print("Codename:", helpers.irecovery_info(irecovery, "MODEL"))
    print("CPU:", helpers.irecovery_info(irecovery, "CPID")[2:])

    return 0


def irecovery_reset(ecid: int, auto_boot: bool = True) -> None:
    helpers.irecovery_command(
        f"setenv auto-boot {'true' if auto_boot else 'false'}", ecid
    )
    helpers.irecovery_command("saveenv", ecid)
    helpers.irecovery_command("reboot", ecid)


async def func_exit_recovery(dev: usb.core.Device, irecovery: str) -> int:
    ecid = int(helpers.irecovery_info(irecovery, "ECID"), 16)

    print(f"Telling device {ecid} to exit recovery.", flush=True)
    irecovery_reset(ecid, auto_boot=True)
    print(f"Device {ecid} has exited recovery", flush=True)

    return 0


async def func_reboot_recovery(dev: usb.core.Device, irecovery: str) -> int:
    ecid = int(helpers.irecovery_info(irecovery, "ECID"), 16)

    print(f"Telling device {ecid} to reboot recovery.", flush=True)
    irecovery_reset(ecid, auto_boot=False)
    print(f"Device {ecid} has rebooted to recovery", flush=True)

    return 0


async def func_dfu_helper(dev: usb.core.Device, irecovery: str) -> int:
    ecid = int(helpers.irecovery_info(irecovery, "ECID"), 16)
    input(
        "Hold down buttons 1 & 2 on the device (and keep holding until this program says stop) and press enter."
    )

    irecovery_reset(ecid, auto_boot=False)

    await asyncio.sleep(2.5)

    print("Release button 1. Keep holding button 2")

    info_task = asyncio.create_task(
        print_in(8, "Whoops. Device did not enter DFU mode. Waiting for re-connect.")
    )
    dev = await helpers.wait_device()
    canceled = info_task.cancel()

    # Now actually check if the device entered DFU
    mode = helpers.classify_mode(dev)

    match mode:
        case helpers.DeviceMode.NORMAL:
            if canceled:
                # Print the message now if it wasn't printed before
                print("Whoops. Device did not enter DFU mode.")
            print("Device re-connected in normal mode.")
            return await normal.run_subcommand(dev, normal.func_dfu_helper)
        case helpers.DeviceMode.RECOVERY:
            if canceled:
                # Print the message now if it wasn't printed before
                print("Whoops. Device did not enter DFU mode.")
            print("Device re-connected in recovery mode.")
            return await run_subcommand(dev, func_dfu_helper)
        case helpers.DeviceMode.DFU:
            print("Device entered DFU mode successfully!")

    return 0


async def main(dev: usb.core.Device, parser: argparse.ArgumentParser):
    subparsers = parser.add_subparsers(required=True)

    subparsers.add_parser("info", help="Print device info").set_defaults(func=func_info)

    reboot_parser = subparsers.add_parser("reboot", help="Reboot device")
    reboot_parser.set_defaults(func=func_exit_recovery)
    reboot_subcommands = reboot_parser.add_subparsers(help="Reboot mode")

    reboot_subcommands.add_parser("system", help="Reboot into iOS (default)")
    reboot_subcommands.add_parser("recovery", help="Reboot into recovery").set_defaults(
        func=func_reboot_recovery
    )
    reboot_subcommands.add_parser(
        "dfu", help="Reboot into dfu (not automatic!)"
    ).set_defaults(func=func_dfu_helper)

    args = parser.parse_args()

    return await run_subcommand(dev, args.func)


# This can be called easily from other python files
async def run_subcommand(dev: usb.core.Device, subcommand: Callable) -> int:
    try:
        serial = dev.serial_number
    except ValueError as e:
        raise ValueError(
            "This script must be run as root for iPhones in recovery or dfu mode."
        ) from e
    # hex(int()) used to add a leading 0x
    irecovery = subprocess.check_output(
        ["irecovery", "-q", "-i", hex(int(helpers.serial_info(serial, "ECID"), 16))]
    ).decode()

    return await subcommand(dev, irecovery)
