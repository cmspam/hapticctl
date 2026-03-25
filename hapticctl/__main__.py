#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# hapticctl — HID haptic touchpad intensity controller for Linux

"""
hapticctl: control haptic feedback intensity on precision touchpads via HID.

Usage:
  hapticctl [OPTIONS] COMMAND [ARGS]

Commands:
  get                  Print current intensity value
  set <value>          Set intensity to a specific value (0-100)
  up                   Step up to next preset level
  down                 Step down to next preset level
  cycle                Cycle through preset levels (wraps around)
  restore              Restore last saved intensity (used by systemd service)
  list-devices         List compatible HID devices found on this system
  status               Show full status (device, intensity, level name)
"""

import argparse
import fcntl
import glob
import os
import struct
import subprocess
import sys
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────

VERSION = "0.1.0"

HID_HAPTIC_PAGE = 0x0E
HID_HAPTIC_INTENSITY_USAGE = 0x23

# Default preset levels: (name, value)
DEFAULT_LEVELS = [
    ("off",    0),
    ("low",   25),
    ("medium", 50),
    ("high",   75),
    ("max",   100),
]

# State file location (XDG_STATE_HOME or fallback)
def state_file() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    p = Path(xdg) / "hapticctl"
    p.mkdir(parents=True, exist_ok=True)
    return p / "intensity"

# System-wide state (when run as root / from systemd system service)
SYSTEM_STATE_FILE = Path("/var/lib/hapticctl/intensity")


# ── HID I/O ────────────────────────────────────────────────────────────────

def _HIDIOCSFEATURE(length: int) -> int:
    return (3 << 30) | (0x48 << 8) | 0x06 | (length << 16)

def _HIDIOCGFEATURE(length: int) -> int:
    return (3 << 30) | (0x48 << 8) | 0x07 | (length << 16)

def _read_hid_report_descriptor(hidraw_path: str) -> bytes:
    """Read the HID report descriptor for a hidraw device."""
    # /sys/class/hidraw/hidrawN/device/report_descriptor
    name = Path(hidraw_path).name  # e.g. hidraw0
    desc_path = Path(f"/sys/class/hidraw/{name}/device/report_descriptor")
    if desc_path.exists():
        return desc_path.read_bytes()
    return b""

def _is_haptic_intensity_device(hidraw_path: str) -> bool:
    """
    Heuristic: check the report descriptor for Haptic page (0x0E) usage.
    Falls back to trying to open and probe if descriptor is unreadable.
    """
    desc = _read_hid_report_descriptor(hidraw_path)
    if not desc:
        return False
    # Look for Usage Page 0x0E (Haptic) — encoded as 05 0E in HID descriptor
    return b'\x05\x0e' in desc.lower() or b'\x05\x0E' in desc

def _device_name(hidraw_path: str) -> str:
    name = Path(hidraw_path).name
    uevent = Path(f"/sys/class/hidraw/{name}/device/uevent")
    if uevent.exists():
        for line in uevent.read_text().splitlines():
            if line.startswith("HID_NAME="):
                return line.split("=", 1)[1]
    return "Unknown device"

def find_haptic_devices() -> list[tuple[str, str]]:
    """Return list of (path, name) for hidraw devices with haptic intensity."""
    results = []
    for path in sorted(glob.glob("/dev/hidraw*")):
        if _is_haptic_intensity_device(path):
            results.append((path, _device_name(path)))
    return results

def _auto_device() -> str:
    """Find first compatible device or exit with helpful error."""
    devices = find_haptic_devices()
    if not devices:
        die("No compatible haptic HID device found.\n"
            "Run 'hapticctl list-devices' for diagnostics, or specify --device manually.")
    return devices[0][0]

def hid_set(device: str, report_id: int, value: int) -> None:
    value = max(0, min(255, value))
    buf = struct.pack("BB", report_id, value)
    try:
        with open(device, "rb+", buffering=0) as f:
            fcntl.ioctl(f, _HIDIOCSFEATURE(len(buf)), buf)
    except PermissionError:
        die(f"Permission denied opening {device}.\n"
            "Try running with sudo, or add yourself to the 'input' group,\n"
            "or install the udev rule: see /usr/share/hapticctl/70-hapticctl.rules")
    except OSError as e:
        die(f"Failed to set feature on {device}: {e}")

def hid_get(device: str, report_id: int) -> int | None:
    """Try to read intensity from device. Returns None if device doesn't support reads."""
    import ctypes
    buf = ctypes.create_string_buffer(bytes([report_id, 0]), 2)
    try:
        with open(device, "rb+", buffering=0) as f:
            fcntl.ioctl(f, _HIDIOCGFEATURE(2), buf)
        return buf[1]
    except OSError:
        return None


# ── State persistence ───────────────────────────────────────────────────────

def _pick_state_file(system: bool) -> Path:
    if system or os.geteuid() == 0:
        SYSTEM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        return SYSTEM_STATE_FILE
    return state_file()

def save_state(value: int, system: bool = False) -> None:
    _pick_state_file(system).write_text(str(value))

def load_state(system: bool = False) -> int | None:
    f = _pick_state_file(system)
    if f.exists():
        try:
            return int(f.read_text().strip())
        except ValueError:
            pass
    return None


# ── Preset levels ───────────────────────────────────────────────────────────

def parse_levels(levels_str: str | None) -> list[tuple[str, int]]:
    """Parse a comma-separated 'name:value,...' string or return defaults."""
    if not levels_str:
        return DEFAULT_LEVELS
    levels = []
    for part in levels_str.split(","):
        name, _, val = part.partition(":")
        levels.append((name.strip(), int(val.strip())))
    return sorted(levels, key=lambda x: x[1])

def level_name(value: int, levels: list[tuple[str, int]]) -> str:
    """Return the name of the nearest preset level."""
    closest = min(levels, key=lambda x: abs(x[1] - value))
    return closest[0]

def next_level(current: int, levels: list[tuple[str, int]], direction: int) -> tuple[str, int]:
    """Return the next level up (+1) or down (-1) from current value."""
    values = [v for _, v in levels]
    if direction > 0:
        candidates = [v for v in values if v > current]
        return levels[values.index(min(candidates))] if candidates else levels[-1]
    else:
        candidates = [v for v in values if v < current]
        return levels[values.index(max(candidates))] if candidates else levels[0]

def cycle_level(current: int, levels: list[tuple[str, int]]) -> tuple[str, int]:
    """Return the next level after current (wraps around)."""
    values = [v for _, v in levels]
    # Find current position (nearest)
    closest_idx = min(range(len(values)), key=lambda i: abs(values[i] - current))
    next_idx = (closest_idx + 1) % len(levels)
    return levels[next_idx]


# ── Notifications ───────────────────────────────────────────────────────────

def notify(name: str, value: int, levels: list[tuple[str, int]], notify_send: bool) -> None:
    if not notify_send:
        return
    # Build a visual bar: 5 blocks corresponding to 5 levels
    n_levels = len(levels)
    level_values = [v for _, v in levels]
    closest_idx = min(range(n_levels), key=lambda i: abs(level_values[i] - value))

    filled = "●" * (closest_idx + 1)
    empty  = "○" * (n_levels - closest_idx - 1)
    bar = filled + empty

    body = f"{bar}  {name} ({value})"

    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=hapticctl",
                "--urgency=low",
                "--expire-time=1500",
                "--hint=string:x-kde-display-appname:hapticctl",
                "--hint=string:x-kde-origin-name:hapticctl",
                "--category=device",
                "Haptic Feedback",
                body,
            ],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # notify-send not available, silently skip


# ── Helpers ─────────────────────────────────────────────────────────────────

def die(msg: str) -> None:
    print(f"hapticctl: error: {msg}", file=sys.stderr)
    sys.exit(1)

def print_value(value: int, levels: list[tuple[str, int]], machine: bool = False) -> None:
    if machine:
        print(value)
    else:
        print(f"{value} ({level_name(value, levels)})")


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hapticctl",
        description="Control haptic touchpad feedback intensity on Linux.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=f"hapticctl {VERSION}")
    p.add_argument(
        "--device", "-d", metavar="PATH",
        help="HID raw device path (e.g. /dev/hidraw0). Auto-detected if not specified.",
    )
    p.add_argument(
        "--report-id", "-r", type=int, default=9, metavar="N",
        help="HID feature report ID for haptic intensity (default: 9).",
    )
    p.add_argument(
        "--levels", metavar="LEVELS",
        help="Comma-separated preset levels as 'name:value' pairs, "
             "e.g. 'off:0,low:25,medium:50,high:75,max:100'.",
    )
    p.add_argument(
        "--notify", "-n", action="store_true",
        help="Send a desktop notification on change (requires notify-send).",
    )
    p.add_argument(
        "--machine", "-m", action="store_true",
        help="Machine-readable output (print only the numeric value).",
    )
    p.add_argument(
        "--system", action="store_true",
        help="Use system-wide state file (/var/lib/hapticctl/intensity) instead of user state.",
    )

    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("get",     help="Print current intensity value.")
    sub.add_parser("restore", help="Restore last saved intensity (for use in systemd service).")
    sub.add_parser("up",      help="Step up to the next preset level.")
    sub.add_parser("down",    help="Step down to the next preset level.")
    sub.add_parser("cycle",   help="Cycle to the next preset level (wraps around).")
    sub.add_parser("status",  help="Show full status: device, value, level name.")
    sub.add_parser("list-devices", help="List compatible HID devices on this system.")

    s = sub.add_parser("set", help="Set intensity to a specific value (0-100).")
    s.add_argument("value", type=int, metavar="VALUE", help="Intensity value (0-100).")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    levels = parse_levels(args.levels)

    # list-devices doesn't need a device
    if args.command == "list-devices":
        devices = find_haptic_devices()
        if not devices:
            print("No compatible haptic HID devices found.")
            print("\nAll hidraw devices on this system:")
            for p in sorted(glob.glob("/dev/hidraw*")):
                print(f"  {p}  ({_device_name(p)})")
        else:
            print("Compatible haptic HID devices:")
            for path, name in devices:
                print(f"  {path}  {name}")
        return

    device = args.device or _auto_device()
    report_id = args.report_id

    if args.command == "get":
        # Try hardware read first, fall back to saved state
        value = hid_get(device, report_id)
        if value is None:
            value = load_state(args.system)
        if value is None:
            die("Could not determine current intensity (device does not support reads and no saved state).")
        print_value(value, levels, args.machine)

    elif args.command == "set":
        value = max(0, min(100, args.value))
        hid_set(device, report_id, value)
        save_state(value, args.system)
        name = level_name(value, levels)
        notify(name, value, levels, args.notify)
        print_value(value, levels, args.machine)

    elif args.command == "up":
        current = load_state(args.system) or 0
        name, value = next_level(current, levels, +1)
        hid_set(device, report_id, value)
        save_state(value, args.system)
        notify(name, value, levels, args.notify)
        print_value(value, levels, args.machine)

    elif args.command == "down":
        current = load_state(args.system) or 0
        name, value = next_level(current, levels, -1)
        hid_set(device, report_id, value)
        save_state(value, args.system)
        notify(name, value, levels, args.notify)
        print_value(value, levels, args.machine)

    elif args.command == "cycle":
        current = load_state(args.system) or 0
        name, value = cycle_level(current, levels)
        hid_set(device, report_id, value)
        save_state(value, args.system)
        notify(name, value, levels, args.notify)
        print_value(value, levels, args.machine)

    elif args.command == "restore":
        value = load_state(args.system)
        if value is None:
            # No saved state: default to medium
            value = DEFAULT_LEVELS[2][1]
        hid_set(device, report_id, value)
        name = level_name(value, levels)
        if not args.machine:
            print(f"Restored haptic intensity to {value} ({name})")

    elif args.command == "status":
        value = hid_get(device, report_id)
        saved = load_state(args.system)
        if value is None:
            value = saved
        if value is None:
            die("No current intensity available.")
        print(f"Device:    {device}")
        print(f"Intensity: {value}")
        print(f"Level:     {level_name(value, levels)}")
        if saved is not None and not args.machine:
            print(f"Saved:     {saved}")


if __name__ == "__main__":
    main()
