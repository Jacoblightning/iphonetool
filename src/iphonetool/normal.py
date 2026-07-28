import argparse
import asyncio
from collections.abc import Callable

import usb.core

try:
    from . import helpers, recovery
except ImportError:
    try:
        import helpers
        import recovery
    except ImportError:
        try:
            from iphonetool import helpers, recovery
        except ImportError:
            raise ImportError("Could not import needed modules")

try:
    import pymobiledevice3.exceptions
    import pymobiledevice3.lockdown
except ImportError:
    print(
        "pymobiledevice3 not installed and is needed for normal/recovery mode operation. Please install pymobiledevice3"
    )
    raise

# Signature of subcommands: lockdown, dev


async def func_info(_dev: usb.core.Device, lockdown) -> int:
    print(f"Detected normal mode {lockdown.display_name}:")
    print("iPhone ID:", lockdown.udid)
    print("iPhone internal version:", lockdown.product_type)
    print("Device name:", lockdown.all_values["DeviceName"])
    print("iOS Version:", lockdown.product_version)
    print("Codename:", lockdown.hardware_model.upper())
    print("CPU:", lockdown.all_values["HardwarePlatform"].upper())

    return 0


async def func_dfu_helper(dev: usb.core.Device, lockdown) -> int:
    # Put device into recovery
    print(f"Telling device {lockdown.udid} to enter recovery.")
    await lockdown.enter_recovery()
    print(f"Device {lockdown.udid} has entered recovery.")

    # Wait for the device to disconnect
    print(
        "Waiting for device disconnect. You may need to re-plug if this takes too long"
    )
    await helpers.wait_disconnect(dev)
    print(f"Device {lockdown.udid} disconnected")

    # Release the old device TODO: Is this needed?
    del dev

    # Get a new device
    print("Waiting for device to reconnect...")
    dev = await helpers.wait_device()

    # Make sure the device is in recovery mode
    mode = helpers.classify_mode(dev)

    match mode:
        case helpers.DeviceMode.NORMAL:
            # Somehow stayed in normal mode
            print("Whoops. Device did not enter recovery mode.")
            return await run_subcommand(dev, func_dfu_helper)
        case helpers.DeviceMode.RECOVERY:
            # Continue dfu helper there
            return await recovery.run_subcommand(dev, recovery.func_dfu_helper)
        case helpers.DeviceMode.DFU:
            # ???
            print("Device entered DFU mode successfully!")
            return 0


async def func_enter_recovery(_dev: usb.core.Device, lockdown) -> int:
    print(f"Telling device {lockdown.udid} to enter recovery.")
    await lockdown.enter_recovery()
    print(f"Device {lockdown.udid} has entered recovery.")

    return 0


async def main(dev: usb.core.Device, parser: argparse.ArgumentParser) -> int:
    subparsers = parser.add_subparsers(required=True)

    subparsers.add_parser("info", help="Print device info").set_defaults(func=func_info)
    subparsers.add_parser(
        "dfu_helper", help="Help put device into DFU mode"
    ).set_defaults(func=func_dfu_helper)
    subparsers.add_parser("enter_recovery", help="Enter recovery mode").set_defaults(
        func=func_enter_recovery
    )

    args = parser.parse_args()

    return await run_subcommand(dev, args.func)


async def run_subcommand(dev: usb.core.Device, subcommand: Callable) -> int:
    serial = dev.serial_number.rstrip("\x00")

    while True:
        try:
            connector = await pymobiledevice3.lockdown.create_using_usbmux(
                connection_type="USB", serial=serial
            )
            break
        except (
            pymobiledevice3.exceptions.DeviceNotFoundError,
            pymobiledevice3.exceptions.ConnectionFailedToUsbmuxdError,
        ):
            # usbmuxd needs a little time sometimes
            print("Failed to connect. Retrying...")
            await asyncio.sleep(0.3)
            continue
        except pymobiledevice3.exceptions.MissingValueError as e:
            # THis can occur if the attempt to connect is made while the device is shutting down
            raise ValueError("Failed to connect to device") from e

    async with connector as lockdown:
        return await subcommand(dev, lockdown)
