# Changelog

All notable changes to hapticctl will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-03-26

### Added
- Initial release
- `get`, `set`, `up`, `down`, `cycle`, `restore`, `status`, `list-devices` commands
- Auto-detection of compatible hidraw devices via HID report descriptor scanning
- Per-user state persistence under `$XDG_STATE_HOME/hapticctl/intensity`
- System-wide state support (`--system`) for boot-time restore
- Desktop notifications via `notify-send` with visual level indicator (`--notify`)
- Machine-readable output mode (`--machine`)
- Configurable preset levels via `--levels`
- systemd user service (`hapticctl-restore.service`)
- systemd system service (`hapticctl-restore-system.service`)
- udev rule for non-root access (`70-hapticctl.rules`)
- Nix flake with NixOS module and Home Manager module
- Man page (`hapticctl.1`)
