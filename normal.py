import usb.core

import argparse
import asyncio

import recovery

import helpers

try:
    import pymobiledevice3.lockdown
    import pymobiledevice3.exceptions
except ImportError:
    print("pymobiledevice3 not installed and is needed for normal/recovery mode operation. Please install pymobiledevice3")
    raise

async def main(dev: usb.core.Device, parser: argparse.ArgumentParser, subparsers: argparse._SubParsersAction) -> int:
    subparsers.add_parser("dfu_helper", help="Help put device into DFU mode")
    subparsers.add_parser("enter_recovery", help="Enter recovery mode")

    args = parser.parse_args()

    return await main_real(dev, args.action)


# This can be called easily from other python files
async def main_real(dev: usb.core.Device, action: str) -> int:
    serial = dev.serial_number.rstrip("\x00")

    while True:
        try:
            connector = await pymobiledevice3.lockdown.create_using_usbmux(connection_type="USB", serial=serial)
            break
        except (pymobiledevice3.exceptions.DeviceNotFoundError, pymobiledevice3.exceptions.ConnectionFailedToUsbmuxdError):
            # usbmuxd needs a little time sometimes
            print("Failed to connect. Retrying...")
            await asyncio.sleep(0.3)
            continue
        except pymobiledevice3.exceptions.MissingValueError as e:
            # THis can occur if the attempt to connect is made while the device is shutting down
            raise ValueError("Failed to connect to device") from e

    async with connector as lockdown:
        match action:
            case "info":
                print(f"Detected normal mode {lockdown.display_name}:")
                print("iPhone ID:", lockdown.udid)
                print("iPhone internal version:", lockdown.product_type)
                print("Device name:", lockdown.all_values["DeviceName"])
                print("iOS Version:", lockdown.product_version)
                print("Codename:", lockdown.hardware_model.upper())
                print("CPU:", lockdown.all_values["HardwarePlatform"].upper())
            case "enter_recovery":
                print(f"Telling device {lockdown.udid} to enter recovery.")
                await lockdown.enter_recovery()
                print(f"Device {lockdown.udid} has entered recovery.")
            case "dfu_helper":
                # Put device into recovery
                print(f"Telling device {lockdown.udid} to enter recovery.")
                await lockdown.enter_recovery()
                print(f"Device {lockdown.udid} has entered recovery.")

                # Wait for the device to disconnect
                print("Waiting for device disconnect.")
                await helpers.wait_disconnect(dev)
                print(f"Device {lockdown.uuid} disconnected")

                # Release the old device
                del dev

                # Get a new device
                print("Waiting for device to reconnect...")
                dev = await helpers.wait_device()

                # Continue dfu helper there
                return await recovery.main_real(dev, "dfu_helper")

    return 0
