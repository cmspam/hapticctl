# hapticctl

**hapticctl** controls the haptic feedback ("click feel") intensity of precision touchpads on Linux.

Modern laptops increasingly ship with haptic touchpads — touchpads with no physical hinge that simulate the sensation of a click using a vibration motor. Windows exposes a slider to tune this feel. Linux has no equivalent. hapticctl fixes that.

It talks directly to the touchpad via the kernel `hidraw` interface, using the [Microsoft Precision Touchpad](https://docs.microsoft.com/en-us/windows-hardware/design/component-guidelines/windows-precision-touchpad-required-hid-descriptors) HID haptic intensity feature report.

```
$ hapticctl cycle --notify
50 (medium)
```

---

## Features

- **Set intensity** to any value 0–100, or step through named presets (off / low / medium / high / max)
- **Cycle** through levels — bind `hapticctl --notify cycle` to a keyboard shortcut
- **Persist state** — saves your setting; restored automatically on login via systemd
- **Auto-detects** compatible hidraw devices by scanning HID report descriptors
- **Desktop notifications** with a visual level indicator (via `notify-send`, works on KDE/GNOME/etc.)
- **Machine-readable output** for scripting
- **Nix flake** with NixOS module and Home Manager module
- **No dependencies** — pure Python 3, no third-party packages required

---

## Compatibility

hapticctl works with any touchpad that exposes HID Usage Page 0x0E (Haptic), Usage 0x23 (Intensity) — as defined in the Windows Precision Touchpad specification. This includes touchpads found in many recent ThinkPads, Dell XPS, Framework laptops, and others.

To check if your device is compatible:

```bash
hapticctl list-devices
```

If nothing is found, install [`hid-feature`](https://github.com/nicoulaj/hid-utils) and run:

```bash
sudo hid-feature list /dev/hidraw0 | grep -i haptic
```

A line like `90000 | 9 | Haptic | Intensity | [0, 100]` means your device is supported.

> **Note:** Many haptic touchpads accept the `SET_FEATURE` ioctl but reject `GET_FEATURE` — meaning hapticctl can set the intensity but cannot read it back from hardware. This is normal. hapticctl works around this by saving the last-set value to disk.

---

## Installation


### From source

```bash
git clone https://github.com/cmspam/hapticctl
cd hapticctl
pip install .
```

### Nix flake

```bash
nix profile install github:cmspam/hapticctl
```

Or in your `flake.nix`:

```nix
inputs.hapticctl.url = "github:cmspam/hapticctl";
```

---

## Permissions

hapticctl requires read/write access to `/dev/hidrawN`. By default this requires root.

Install the provided udev rule to allow members of the `input` group to use hapticctl without sudo:

```bash
sudo cp contrib/70-hapticctl.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG input $USER
# Log out and back in for the group change to take effect
```

---

## Usage

```
hapticctl [OPTIONS] COMMAND [ARGS]

Commands:
  get           Print current intensity
  set VALUE     Set intensity (0-100)
  up            Step up to next preset level
  down          Step down to next preset level
  cycle         Cycle to next preset level (wraps around)
  restore       Restore last saved intensity
  status        Show device, intensity, and level name
  list-devices  List compatible HID devices on this system

Options:
  -d, --device PATH     HID device path (auto-detected if omitted)
  -r, --report-id N     Feature report ID (default: 9)
  --levels LEVELS       Custom preset levels, e.g. 'off:0,low:33,max:100'
  -n, --notify          Send desktop notification on change
  -m, --machine         Machine-readable output (numeric value only)
  --system              Use system-wide state file
  --version             Show version
```

### Examples

```bash
# Set to maximum
hapticctl set 100

# Step up one level, show a notification
hapticctl --notify up

# Cycle through levels (great for a keyboard shortcut)
hapticctl --notify cycle

# Print current value as a number (for scripts/waybar/etc.)
hapticctl --machine get

# See what's going on
hapticctl status
```

---

## Keyboard shortcut (KDE)

Go to **System Settings → Shortcuts → Custom Shortcuts**, add a new shortcut, and set the command to:

```
hapticctl --notify cycle
```

Assign your preferred key combination. Now you can cycle through click feels on the fly.

For **GNOME** or other desktops, use your desktop's shortcut settings with the same command.

---

## Systemd service (restore on login)

### User service (recommended)

```bash
mkdir -p ~/.config/systemd/user/
cp systemd/hapticctl-restore.service ~/.config/systemd/user/
systemctl --user enable --now hapticctl-restore.service
```

### System service (restore at boot, before login)

```bash
sudo cp systemd/hapticctl-restore-system.service /etc/systemd/system/
sudo systemctl enable --now hapticctl-restore-system.service
```

Use `hapticctl --system set VALUE` when using the system service, so it reads and writes `/var/lib/hapticctl/intensity`.

---

## NixOS module

```nix
# flake.nix
{
  inputs.hapticctl.url = "github:cmspam/hapticctl";

  outputs = { nixpkgs, hapticctl, ... }: {
    nixosConfigurations.mymachine = nixpkgs.lib.nixosSystem {
      modules = [
        hapticctl.nixosModules.default
        {
          services.hapticctl = {
            enable = true;
            defaultIntensity = 50;
          };
        }
      ];
    };
  };
}
```

## How it works

Haptic touchpads implement the [HID Haptics](https://usb.org/sites/default/files/hut1_5.pdf) usage page (0x0E). Specifically, they expose a Feature Report containing Usage 0x23 (Intensity), accepting values 0–100.

On Windows, the precision touchpad driver reads and writes this report transparently. On Linux, the kernel exposes the raw device as `/dev/hidrawN`, and no higher-level software has historically touched this report.

hapticctl sends a `HIDIOCSFEATURE` ioctl directly to `/dev/hidrawN`, bypassing libinput entirely. Many devices accept writes but reject reads (`HIDIOCGFEATURE` returns `EINVAL`); hapticctl handles this gracefully by maintaining its own state file.

---


## License

[MIT](LICENSE) © cmspam
