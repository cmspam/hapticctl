# Contributing

Contributions are welcome! Here's how to get started.

## Development setup

```bash
git clone https://github.com/cmspam/hapticctl
cd hapticctl
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with Nix:

```bash
nix develop
```

## Testing

hapticctl is a hardware interface tool, so automated testing is limited without
a compatible device. If you have one, run through the main commands manually:

```bash
hapticctl list-devices
hapticctl set 50
hapticctl get
hapticctl up
hapticctl down
hapticctl cycle
hapticctl status
hapticctl restore
```

## Adding support for new devices

If your device uses a different HID report ID for haptic intensity, you can use:

```bash
hid-feature list /dev/hidrawN | grep -i haptic
```

...and then pass `--report-id N` to hapticctl. If you find a device that works
with a non-default report ID, please open an issue or PR with the device's
USB vendor/product ID so it can be auto-detected.

## Submitting changes

- Keep commits focused and atomic
- Update CHANGELOG.md under `[Unreleased]`
- Update the man page if you change CLI behaviour
- Open a pull request against `main`
