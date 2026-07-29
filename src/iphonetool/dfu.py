import argparse
import asyncio
import glob
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.parse
import tempfile
import remotezip
from collections.abc import Callable
from enum import IntEnum, auto
from typing import Any, Optional

import requests
import usb.core

try:
    from . import config, helpers, normal, recovery
except ImportError:
    try:
        import config  # type: ignore
        import helpers  # type: ignore
        import normal  # type: ignore
        import recovery  # type: ignore
    except ImportError:
        try:
            from iphonetool import config, helpers, normal, recovery
        except ImportError:
            raise ImportError("Could not import needed modules")


async def func_info(
    dev: usb.core.Device, irecovery: str, pwned: bool, _args: argparse.Namespace
) -> int:
    if pwned:
        print(f"Detected PWNED DFU mode {helpers.irecovery_info(irecovery, "NAME")}:")
    else:
        print(f"Detected DFU mode {helpers.irecovery_info(irecovery, "NAME")}:")
    print("iPhone ID:", helpers.irecovery_info(irecovery, "ECID"))
    print("iPhone internal version:", helpers.irecovery_info(irecovery, "PRODUCT"))
    print("Codename:", helpers.irecovery_info(irecovery, "MODEL"))
    print("CPU:", helpers.irecovery_info(irecovery, "CPID")[2:])

    return 0


async def download_device_iboot(irecovery: str, output_path: pathlib.Path):
    product_code = helpers.irecovery_info(irecovery, "PRODUCT")

    print("Checking IPSWs...")

    ipsw_urls = requests.get(f"https://api.ipsw.me/v4/ipsw/device/{urllib.parse.quote(product_code)}").json()

    ipsw_url = ipsw_urls["firmwares"][-1]["url"]  # Take the last (oldest) one as it will be the smallest

    with tempfile.TemporaryDirectory() as enc_extract_dir:
        # Download and extract the (encrypted) iboot
        print("Downlading and extracting...")

        board_version = helpers.irecovery_info(irecovery, "MODEL").lower()[:-2]
        iboot_zipf = f"Firmware/all_flash/iBoot.{board_version}.RELEASE.im4p"


        with remotezip.RemoteZip(ipsw_url) as zipf:
            zipf.extract(iboot_zipf, enc_extract_dir)

        # Decrypt the extracted file

        enc_file = pathlib.Path(enc_extract_dir) / iboot_zipf

        iOS_build = ipsw_url.split("_")[-2]

        print("Decrypting...")

        subprocess.check_call(
            [
                "ipsw",
                "-V",
                "img4",
                "im4p",
                "extract",
                "--lookup",
                "--lookup-device",
                product_code,
                "--lookup-build",
                iOS_build,
                "--output",
                output_path,
                enc_file,
            ]
        )


class RebootTarget(IntEnum):
    SYSTEM = auto()
    RECOVERY = auto()
    DFU = auto()


async def func_reboot(
    dev: usb.core.Device, irecovery: str, args: argparse.Namespace, target: RebootTarget
) -> int:
    if args.iboot is not None:
        if args.iboot.is_dir():
            raise ValueError("iboot must be a file")
        if not args.iboot.exists():
            await download_device_iboot(irecovery, args.iboot)
        usbliter8_boot(dev, args.iboot.read_bytes())
    else:
        with tempfile.TemporaryDirectory() as output_tempdir:
            output = pathlib.Path(output_tempdir) / "iboot.macho"
            await download_device_iboot(irecovery, output)
            usbliter8_boot(dev, output.read_bytes())

    print("Waiting for device to switch into recovery")
    await helpers.wait_disconnect(dev)
    del dev
    dev = await helpers.wait_device()

    mode = helpers.classify_mode(dev)

    match mode:
        case helpers.DeviceMode.NORMAL:
            match target:
                case RebootTarget.SYSTEM:
                    print("Device has exited DFU")
                case RebootTarget.RECOVERY:
                    return await normal.run_subcommand(dev, normal.func_reboot_recovery)
                case RebootTarget.DFU:
                    return await normal.run_subcommand(dev, normal.func_dfu_helper)
        case helpers.DeviceMode.RECOVERY:
            match target:
                case RebootTarget.SYSTEM:
                    return await recovery.run_subcommand(
                        dev, recovery.func_exit_recovery
                    )
                case RebootTarget.RECOVERY:
                    # Reboot into normal recovery. not iBoot recovery
                    return await recovery.run_subcommand(
                        dev, recovery.func_reboot_recovery
                    )
                case RebootTarget.DFU:
                    return await recovery.run_subcommand(dev, recovery.func_dfu_helper)
        case helpers.DeviceMode.DFU:
            # ???
            print("Failed to exit DFU mode.")
            return 1

    return 0


async def func_reboot_ios(
    dev: usb.core.Device, irecovery: str, _pwned: bool, args: argparse.Namespace
) -> int:
    return await func_reboot(dev, irecovery, args, RebootTarget.SYSTEM)


async def func_reboot_recovery(
    dev: usb.core.Device, irecovery: str, _pwned: bool, args: argparse.Namespace
) -> int:
    return await func_reboot(dev, irecovery, args, RebootTarget.RECOVERY)


async def func_reboot_dfu(
    dev: usb.core.Device, irecovery: str, _pwned: bool, args: argparse.Namespace
) -> int:
    return await func_reboot(dev, irecovery, args, RebootTarget.DFU)


async def func_demote(
    dev: usb.core.Device, irecovery: str, _pwned: bool, _args: argparse.Namespace
) -> int:
    ecid = helpers.irecovery_info(irecovery, "ECID")
    print(f"Telling device {ecid} to demote to development.")
    send_usbliter8_command(dev, Usbliter8Command.CUSTOM_DEMOTE, None, 100)
    print(f"Device {ecid} has demoted to development.")

    return 0


async def func_boot_raw(
    dev: usb.core.Device, _irecovery: str, _pwned: bool, args: argparse.Namespace
) -> int:
    iboot_file = args.iboot
    print(f"Uploading {iboot_file} to device...")
    usbliter8_boot(dev, iboot_file.read_bytes())

    return 0


async def func_boot_remote(
    dev: usb.core.Device, _irecovery: str, _pwned: bool, args: argparse.Namespace
) -> int:
    linux_remote_boot(args.m1n1, args.monitor, args.remoteboot)

    return 0


async def func_boot_linux(
    dev: usb.core.Device, _irecovery: str, _pwned: bool, args: argparse.Namespace
) -> int:
    print("Preapring iboot...")
    with tempfile.NamedTemporaryFile(mode="wb") as m1n1_blob_file:
        print("adding m1n1")
        with args.m1n1.open("rb") as f:
            shutil.copyfileobj(f, m1n1_blob_file)
        if args.commandline is not None:
            print("adding commandline")
            m1n1_blob_file.write(f"chosen.bootargs={args.commandline}\n".encode())
        if args.dtb is not None:
            if not args.dtb.is_file():
                raise ValueError("Specified DTB is not a file.")
            print("adding dtb")
            with args.dtb.open("rb") as f:
                shutil.copyfileobj(f, m1n1_blob_file)
        else:
            if not args.dtbs.is_dir():
                raise ValueError("Specified DTB directory is not a dir.")
            print("adding dtbs")
            for dtb in glob.iglob("./*.dtb", root_dir=args.dtbs):
                with (args.dtbs / dtb).open("rb") as f:
                    shutil.copyfileobj(f, m1n1_blob_file)
        print("adding kernel")
        with args.kernel.open("rb") as f:
            shutil.copyfileobj(f, m1n1_blob_file)
        if args.initramfs is not None:
            print("adding initramfs")
            with args.initramfs.open("rb") as f:
                shutil.copyfileobj(f, m1n1_blob_file)
        linux_remote_boot(
            pathlib.Path(m1n1_blob_file.name), args.monitor, args.remoteboot
        )

    return 0


async def main(dev: usb.core.Device, parser: argparse.ArgumentParser):
    subparsers = parser.add_subparsers(required=True)

    subparsers.add_parser("info", help="Print device info").set_defaults(func=func_info)

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
        ).set_defaults(func=func_demote)

        reboot_parser = subparsers.add_parser("reboot", help="Reboot device")
        reboot_parser.set_defaults(func=func_reboot_ios)
        reboot_parser.add_argument(
            "--iboot",
            type=pathlib.Path,
            help="Path to an iboot file to save/load. If it does not exist, the needed file will be downloaded and moved there. If not specified, a temporary location will be used.",
        )
        reboot_subcommands = reboot_parser.add_subparsers(help="Reboot mode")

        reboot_subcommands.add_parser("system", help="Reboot into iOS (default)")
        reboot_subcommands.add_parser(
            "recovery", help="Reboot into recovery"
        ).set_defaults(func=func_reboot_recovery)
        reboot_subcommands.add_parser(
            "dfu", help="Reboot into dfu (not automatic!)"
        ).set_defaults(func=func_reboot_dfu)

        boot_parser = subparsers.add_parser(
            "boot", help='Low-level device exploit booting. You probably want "linux"'
        )
        boot_subparsers = boot_parser.add_subparsers(dest="boot_action")

        boot_raw_parser = boot_subparsers.add_parser(
            "raw", help="Boot a raw iBoot file"
        )
        boot_raw_parser.add_argument(
            "iboot", type=pathlib.Path, help="The raw iBoot to boot"
        )
        boot_raw_parser.set_defaults(func=func_boot_raw)

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
        boot_remote_parser.add_argument(
            "--remoteboot",
            type=pathlib.Path,
            help="Path to remoteboot.sh",
            required=True,
        )
        boot_remote_parser.set_defaults(func=func_boot_remote)

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
        linux_parser.add_argument(
            "--remoteboot",
            type=pathlib.Path,
            help="Path to remoteboot.sh",
            required=True,
        )
        linux_parser.set_defaults(func=func_boot_linux)

    args = parser.parse_args()

    return await run_subcommand(dev, pwned_device, serial, args.func, args)


class Usbliter8Command(IntEnum):
    DFU_DNLOAD = 1
    DFU_ABORT = 4
    CUSTOM_DEMOTE = 7
    CUSTOM_BOOT = 8


def send_usbliter8_command(
    dev: usb.core.Device, command: Usbliter8Command, data: Any, timeout: int
) -> None:
    dev.ctrl_transfer(0x21, command, 0, 0, data, timeout)


def usbliter8_download(dev: usb.core.Device, data: bytes) -> None:
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


def usbliter8_boot(dev: usb.core.Device, data: bytes) -> None:
    usbliter8_download(dev, data)

    send_usbliter8_command(dev, Usbliter8Command.CUSTOM_BOOT, None, 100)
    send_usbliter8_command(dev, Usbliter8Command.DFU_ABORT, None, 100)


def linux_remote_boot(
    m1n1_blob: pathlib.Path,
    monitor_stub: Optional[pathlib.Path],
    remoteboot: pathlib.Path,
):
    if monitor_stub is not None:
        subprocess.check_call(
            [
                "bash",
                remoteboot,
                "boot",
                m1n1_blob,
                monitor_stub,
            ],
            env={  # type: ignore
                "USBLITER8CTL": helpers.base_directory() / "usbliter8ctl.py",
                "PYTHON": sys.executable,
                "HOME": os.getenv("HOME", "~"),
            },
        )
    else:
        subprocess.check_call(
            ["bash", remoteboot, "boot", m1n1_blob],
            env={  # type: ignore
                "USBLITER8CTL": helpers.base_directory() / "usbliter8ctl.py",
                "PYTHON": sys.executable,
                "HOME": os.getenv("HOME", "~"),
            },
        )


def linux_prep():
    parser = argparse.ArgumentParser()
    parser.add_argument("remoteboot", type=pathlib.Path, help="Path to remoteboot.sh")

    args = parser.parse_args()

    subprocess.check_call(["bash", args.remoteboot, "build"])
    subprocess.check_call(["sudo", "bash", args.remoteboot, "prep"])
    print("You can now boot linux on your device")


async def run_subcommand(
    dev: usb.core.Device,
    pwned: bool,
    serial: str,
    func: Callable,
    args: argparse.Namespace,
) -> int:
    ecid = int(helpers.serial_info(serial, "ECID"), 16)

    irecovery = subprocess.check_output(["irecovery", "-q", "-i", hex(ecid)]).decode()

    return await func(dev, irecovery, pwned, args)
