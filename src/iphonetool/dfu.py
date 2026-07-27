import argparse
import asyncio
import glob
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from enum import IntEnum
from typing import Any, Optional

import usb.core

from . import config
from . import helpers


async def main(
    dev: usb.core.Device,
    parser: argparse.ArgumentParser,
    subparsers: argparse._SubParsersAction,
):
    subparsers.add_parser("exit_dfu_helper", help="Help exiting DFU mode")

    try:
        serial = dev.serial_number
    except ValueError as e:
        raise ValueError(
            "This script must be run as root for iPhones in recovery or dfu mode."
        ) from e

    if helpers.serial_info_get(serial, "PWND") == "[usbliter8]":
        pwned_device = True
    else:
        pwned_device = False

    if pwned_device:
        subparsers.add_parser(
            "demote", help="Demote this device to a development device"
        )

        boot_parser = subparsers.add_parser(
            "boot", help='Low-level device exploit booting. You probably want "linux"'
        )
        boot_subparsers = boot_parser.add_subparsers(dest="boot_action")

        boot_raw_parser = boot_subparsers.add_parser(
            "raw", help="Boot a raw iBoot file"
        )
        boot_raw_parser.add_argument(
            "iBoot", type=pathlib.Path, help="The raw iBoot to boot"
        )

        boot_remote_parser = boot_subparsers.add_parser(
            "remote", help="Remote boot m1n1, linux, etc."
        )
        boot_remote_parser.add_argument(
            "-1",
            "--m1n1",
            type=pathlib.Path,
            help="m1n1-idevice.macho + any addons (linux, dtbs, etc)",
            required=True,
        )
        boot_remote_parser.add_argument(
            "-m", "--monitor", type=pathlib.Path, help="m1n1 monitor stub"
        )
        boot_remote_parser.add_argument("--remoteboot", type=pathlib.Path, help="Path to remoteboot.sh", required=True)

        # High-level linux booter
        linux_parser = subparsers.add_parser("linux", help="Boot linux on device")
        linux_parser.add_argument(
            "-1",
            "--m1n1",
            type=pathlib.Path,
            help="Path to m1n1-idevice.macho",
            required=True,
        )
        linux_parser_dtb_group = linux_parser.add_mutually_exclusive_group(
            required=True
        )
        linux_parser_dtb_group.add_argument(
            "-d", "--dtb", type=pathlib.Path, help="Path to devicetree for device"
        )
        linux_parser_dtb_group.add_argument(
            "-D", "--dtbs", type=pathlib.Path, help="Path to directory of devicetrees"
        )
        linux_parser.add_argument(
            "-k", "--kernel", type=pathlib.Path, help="Path to kernel", required=True
        )
        linux_parser.add_argument(
            "-c", "--commandline", help="Linux commandline to boot"
        )
        linux_parser.add_argument(
            "-i", "--initramfs", type=pathlib.Path, help="Linux initramfs to boot"
        )
        linux_parser.add_argument(
            "-m", "--monitor", type=pathlib.Path, help="m1n1 monitor stub"
        )
        linux_parser.add_argument("--remoteboot", type=pathlib.Path, help="Path to remoteboot.sh", required=True)

    args = parser.parse_args()

    return await main_real(dev, pwned_device, serial, args.action, vars(args))


class Usbliter8Command(IntEnum):
    DFU_DNLOAD = 1
    DFU_ABORT = 4
    CUSTOM_DEMOTE = 7
    CUSTOM_BOOT = 8


def send_usbliter8_command(
    dev: usb.core.Device, command: Usbliter8Command, data: Any, timeout: int
) -> None:
    dev.ctrl_transfer(0x21, command, 0, 0, data, timeout)


def usbliter8_download(dev: usb.core.Device, data: bytes) -> True:
    offset = 0
    left = len(data)

    while left:
        current_block_length = min(config.USBLITER8_TRANSFER_SIZE, left)

        send_usbliter8_command(
            dev,
            Usbliter8Command.DFU_DNLOAD,
            data[offset : offset + current_block_length],
            1000,
        )

        offset += current_block_length
        left -= current_block_length

        print(f"\rUploaded: 0x{offset:x}/0x{len(data):x} bytes.", end="")

    print()

    send_usbliter8_command(dev, Usbliter8Command.DFU_DNLOAD, None, 100)


def linux_remote_boot(m1n1_blob: pathlib.Path, monitor_stub: Optional[pathlib.Path], remoteboot: pathlib.Path):
    if monitor_stub is not None:
        subprocess.check_call(
            [
                "bash", remoteboot,
                "boot",
                m1n1_blob,
                monitor_stub,
            ],
            env={
                "USBLITER8CTL": helpers.base_directory() / "usbliter8ctl.py",
                "PYTHON": sys.executable,
                "HOME": os.getenv("HOME"),
            },
        )
    else:
        subprocess.check_call(
            ["bash", remoteboot, "boot", m1n1_blob],
            env={
                "USBLITER8CTL": helpers.base_directory() / "usbliter8ctl.py",
                "PYTHON": sys.executable,
                "HOME": os.getenv("HOME"),
            },
        )

def linux_prep():
    parser = argparse.ArgumentParser()
    parser.add_argument("remoteboot", type=pathlib.Path, help="Path to remoteboot.sh")

    args = parser.parse_args()

    subprocess.check_call(
        ["bash", args.remoteboot, "build"]
    )
    subprocess.check_call(
        ["sudo", "bash", args.remoteboot, "prep"]
    )
    print("You can now boot linux on your device")

async def main_real(
    dev: usb.core.Device, pwned: bool, serial: str, action: str, args: dict
) -> int:
    ecid = int(helpers.serial_info(serial, "ECID"), 16)

    irecovery = subprocess.check_output(["irecovery", "-q", "-i", hex(ecid)]).decode()

    match action:
        case "info":
            if pwned:
                print(
                    f"Detected PWNED DFU mode {helpers.irecovery_info(irecovery, "NAME")}:"
                )
            else:
                print(f"Detected DFU mode {helpers.irecovery_info(irecovery, "NAME")}:")
            print("iPhone ID:", ecid)
            print(
                "iPhone internal version:", helpers.irecovery_info(irecovery, "PRODUCT")
            )
            print("Codename:", helpers.irecovery_info(irecovery, "MODEL"))
            print("CPU:", helpers.serial_info(serial, "CPID"))
        case "exit_dfu_helper":
            # TODO: This
            print("Idk. You figure it out")
        case "demote":
            print(f"Telling device {ecid} to demote to development.")
            send_usbliter8_command(dev, Usbliter8Command.CUSTOM_DEMOTE, None, 100)
            print(f"Device {ecid} has demoted to development.")
        case "boot":
            match args["boot_action"]:
                case "raw":
                    iboot_file = args["iBoot"]
                    print(f"Uploading {iboot_file} to device...")
                    usbliter8_download(dev, iboot_file.read_bytes())

                    send_usbliter8_command(dev, Usbliter8Command.CUSTOM_BOOT, None, 100)
                    send_usbliter8_command(dev, Usbliter8Command.DFU_ABORT, None, 100)
                case "remote":
                    linux_remote_boot(args["m1n1"], args.get("monitor"), args["remoteboot"])
        case "linux":
            print("Preapring iboot...")
            with tempfile.NamedTemporaryFile(mode="wb") as m1n1_blob_file:
                print("adding m1n1")
                with args["m1n1"].open("rb") as f:
                    shutil.copyfileobj(f, m1n1_blob_file)
                if args["commandline"] is not None:
                    print("adding commandline")
                    m1n1_blob_file.write(
                        f'chosen.bootargs={args["commandline"]}\n'.encode()
                    )
                if args["dtb"] is not None:
                    if not args["dtb"].is_file():
                        raise ValueError("Specified DTB is not a file.")
                    print("adding dtb")
                    with args["dtb"].open("rb") as f:
                        shutil.copyfileobj(f, m1n1_blob_file)
                else:
                    if not args["dtbs"].is_dir():
                        raise ValueError("Specified DTB directory is not a dir.")
                    print("adding dtbs")
                    for dtb in glob.iglob("./*.dtb", root_dir=args["dtbs"]):
                        with (args["dtbs"] / dtb).open("rb") as f:
                            shutil.copyfileobj(f, m1n1_blob_file)
                print("adding kernel")
                with args["kernel"].open("rb") as f:
                    shutil.copyfileobj(f, m1n1_blob_file)
                if args["initramfs"] is not None:
                    print("adding initramfs")
                    with args["initramfs"].open("rb") as f:
                        shutil.copyfileobj(f, m1n1_blob_file)
                linux_remote_boot(
                    pathlib.Path(m1n1_blob_file.name), args.get("monitor"), args["remoteboot"]
                )

    return 0
