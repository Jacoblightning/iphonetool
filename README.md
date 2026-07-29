# iphonetool

All of the modern iOS tools. Unified.


## Installation

### from pypi (slow updates)

#### pip
`pip install iphonetool`

#### uv
`uv tool install iphonetool`

### from git (fast updates)

#### pip
`pip install git+https://git.jacoblightning3.xyz/jacoblightning3/iphonetool.git@master`

or from	the mirror:

`pip install git+https://github.com/Jacoblightning/iphonetool.git@master`

#### uv
`uv tool install --compile-bytecode  https://git.jacoblightning3.xyz/jacoblightning3/iphonetool.git`

or from the mirror:

`uv tool install --compile-bytecode https://github.com/Jacoblightning/iphonetool.git`

## Prerequisites

> [!IMPORTANT]  
> When you clone [https://github.com/yhavry/remote_boot](https://github.com/yhavry/remote_boot), make sure you switch to the `d421-a12-a13-postpwned-prep` branch!

Before you can run linux (or remote boot) on a phone, you must run `iphonetool-linuxprep` with a path to `remoteboot.sh`, which is located in [https://github.com/yhavry/remote_boot](https://github.com/yhavry/remote_boot)

## Usage

- Run `iphonetool.py info` to give info on connected devices
- Run `iphonetool.py -h` to show help for the current device (this help changes per-device)

## Tools this combines

- `palera1n --dfuhelper`
- `palera1n --exit-recovery`
- `ideviceenterrecovery`
- `remote_booting linux`
- `usbliter8ctl`

## License

`iphonetool` is currently licensed under the GPLv3.
