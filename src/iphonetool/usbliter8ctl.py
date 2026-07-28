#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyusb>=1.3.1",
# ]
# ///

# This is a clone of usbliter8ctl using the helpers in this module.
# Used for remote_boot

import argparse
import pathlib

import usb
from dfu import send_usbliter8_command  # type: ignore
from dfu import Usbliter8Command, usbliter8_download
from helpers import get_device  # type: ignore


def do_boot(args, dev):
    usbliter8_download(dev, args.iboot.read_bytes())

    send_usbliter8_command(dev, Usbliter8Command.CUSTOM_BOOT, None, 100)
    send_usbliter8_command(dev, Usbliter8Command.DFU_ABORT, None, 100)


def do_demote(args, dev):
    send_usbliter8_command(dev, Usbliter8Command.CUSTOM_DEMOTE, None, 100)


def main():
    parser = argparse.ArgumentParser(description="Love is Control")

    subparsers = parser.add_subparsers()

    boot_parser = subparsers.add_parser("boot", help="boot raw iBoot")
    boot_parser.set_defaults(func=do_boot)
    boot_parser.add_argument("iboot", type=pathlib.Path)

    demote_parser = subparsers.add_parser("demote", help="demote production mode")
    demote_parser.set_defaults(func=do_demote)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        exit(-1)

    dev = get_device()

    srnm = dev.serial_number

    if "PWND:[" not in srnm:
        raise RuntimeError("this is not Pwned DFU device")

    args.func(args, dev)


if __name__ == "__main__":
    main()
