import argparse
import asyncio
from collections.abc import Callable
from typing import Optional

import usb.core

try:
    from . import helpers, recovery
except ImportError:
    try:
        import helpers  # type: ignore
        import recovery  # type: ignore
    except ImportError:
        try:
            from iphonetool import helpers, recovery
        except ImportError:
            raise ImportError("Could not import needed modules")

try:
    import pymobiledevice3.exceptions
    import pymobiledevice3.lockdown
    has_all_deps = True
except ImportError:
    has_all_deps = False

# Signature of subcommands: lockdown, dev


async def func_info(_dev: usb.core.Device, lockdown) -> int:
    print(f"Detected normal mode {lockdown.display_name if lockdown.display_name is not None else 'unknown '+lockdown.device_class.value}:")
    print("iPhone ID:", lockdown.udid)
    print("iPhone internal version:", lockdown.product_type if lockdown.product_type is not None else (lockdown.all_values["ProductType"] if "ProductType" in lockdown.all_values else "unknown"))
    print("Device name:", lockdown.all_values["DeviceName"])
    print("iOS Version:", lockdown.product_version)
    print("Codename:", lockdown.hardware_model.upper() if lockdown.hardware_model is not None else (lockdown.all_values["HardwareModel"].upper() if "HardwareModel" in lockdown.all_values else "unknown"))
    print("CPU:", lockdown.all_values["HardwarePlatform"].upper())
    print("Password Protected:", "yes" if lockdown.all_values["PasswordProtected"] else "no")
    print("Model Number:", lockdown.all_values["ModelNumber"])

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
            print("Failed to put device into recovery mode.")
            return 1
        case helpers.DeviceMode.RECOVERY:
            # Continue dfu helper there
            return await recovery.run_subcommand(dev, recovery.func_dfu_helper)
        case helpers.DeviceMode.DFU:
            # ???
            print("Device entered DFU mode successfully!")
            return 0


async def func_reboot_recovery(_dev: usb.core.Device, lockdown) -> int:
    print(f"Telling device {lockdown.udid} to enter recovery.")
    await lockdown.enter_recovery()
    print(f"Device {lockdown.udid} has entered recovery.")

    return 0


async def func_reboot(dev: usb.core.Device, lockdown) -> int:
    print(f"Telling device {lockdown.udid} to reboot.")

    # Slightly cursed...
    await lockdown.enter_recovery()

    await helpers.wait_disconnect(dev)
    del dev
    dev = await helpers.wait_device()

    # Make sure the device is in recovery mode
    mode = helpers.classify_mode(dev)

    match mode:
        case helpers.DeviceMode.NORMAL:
            # Somehow stayed in normal mode
            print("Failed to reboot device.")
            return 1
        case helpers.DeviceMode.RECOVERY:
            # Continue dfu helper there
            return await recovery.run_subcommand(dev, recovery.func_exit_recovery)
        case helpers.DeviceMode.DFU:
            # ??????
            print("Really failed to reboot device!")
            return 1


async def main(dev: Optional[usb.core.Device], parser: argparse.ArgumentParser) -> int:
    subparsers = parser.add_subparsers(required=True)

    subparsers.add_parser("info", help="Print device info").set_defaults(func=func_info)

    reboot_parser = subparsers.add_parser("reboot", help="Reboot device")
    reboot_parser.set_defaults(func=func_reboot)
    reboot_subcommands = reboot_parser.add_subparsers(help="Reboot mode")

    reboot_subcommands.add_parser("system", help="Reboot into iOS (default)")
    reboot_subcommands.add_parser("recovery", help="Reboot into recovery").set_defaults(
        func=func_reboot_recovery
    )
    reboot_subcommands.add_parser(
        "dfu", help="Reboot into dfu (not automatic!)"
    ).set_defaults(func=func_dfu_helper)

    args = parser.parse_args()

    assert dev is not None

    return await run_subcommand(dev, args.func)


async def run_subcommand(dev: usb.core.Device, subcommand: Callable) -> int:
    if not has_all_deps:
        raise ValueError("pymobiledevice3 not installed and is needed for normal/recovery mode operation. Please install pymobiledevice3")

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
