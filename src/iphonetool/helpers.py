import asyncio
import functools
import pathlib
import subprocess
from enum import Enum, auto
from typing import Optional

import usb.core

try:
    from .config import APPLE_VENDORID, AppleProductId
except ImportError:
    try:
        from config import APPLE_VENDORID, AppleProductId
    except ImportError:
        try:
            from iphonetool.config import APPLE_VENDORID, AppleProductId
        except ImportError:
            raise ImportError("Could not import needed modules")


class DeviceMode(Enum):
    NORMAL = auto()
    RECOVERY = auto()
    DFU = auto()


def get_device():
    return usb.core.find(idVendor=APPLE_VENDORID)


async def wait_device():
    while True:
        dev = get_device()
        if dev is not None:
            return dev

        await asyncio.sleep(0.1)


async def wait_disconnect(dev: usb.core.Device):
    while True:
        try:
            device = usb.core.find(idVendor=dev.idVendor, idProduct=dev.idProduct)
            if device is not None and device.serial_number == dev.serial_number:
                await asyncio.sleep(0.1)
                continue
        except ValueError:
            continue
        break


def classify_mode(dev: usb.core.Device) -> DeviceMode:
    match dev.idProduct:
        case AppleProductId.RECOVERY:
            return DeviceMode.RECOVERY
        case AppleProductId.DFU:
            return DeviceMode.DFU
        case _:
            return DeviceMode.NORMAL


def serial_info_get(serial, key) -> Optional[str]:
    value = dict(
        list(map(functools.partial(str.split, sep=":", maxsplit=1), serial.split(" ")))
    ).get(key.upper())
    if value is None:
        return value
    return value.strip()


def serial_info(serial, key) -> str:
    value = serial_info_get(serial, key)
    if value is None:
        raise ValueError(f"Could not find key {key} in recovery serial {serial}")
    return value


def irecovery_info(irecovery, key) -> str:
    try:
        return dict(list(map(functools.partial(str.split, sep=":", maxsplit=1), irecovery.splitlines())))[key.upper()].strip()  # type: ignore
    except IndexError as e:
        raise ValueError(
            f"Could not find key {key} in irecovery data {irecovery}"
        ) from e


def irecovery_command(cmd: str, ecid: Optional[int] = None) -> None:
    if ecid is not None:
        subprocess.run(["irecovery", "-i", hex(ecid), "-c", cmd], check=True)
    else:
        subprocess.run(["irecovery", "-c", cmd], check=True)


def base_directory() -> pathlib.Path:
    script_dir = pathlib.Path(__file__).parent
    #base_dir = script_dir.parent.parent
    #return base_dir
    return script_dir
