{
  description = "hapticctl — haptic touchpad intensity controller for Linux";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${stdenv.hostPlatform.system};
        hapticctl = pkgs.python3Packages.buildPythonApplication {
          pname = "hapticctl";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";
          nativeBuildInputs = [ pkgs.python3Packages.setuptools pkgs.python3Packages.wheel ];
          meta = with pkgs.lib; {
            description = "Control haptic touchpad feedback intensity on Linux via HID";
            homepage = "https://github.com/cmspam/hapticctl";
            license = licenses.mit;
            maintainers = [ ];
            platforms = [ "x86_64-linux" "aarch64-linux" ];
            mainProgram = "hapticctl";
          };
        };
      in
      {
        packages.default = hapticctl;
        packages.hapticctl = hapticctl;

        apps.default = flake-utils.lib.mkApp { drv = hapticctl; };

        devShells.default = pkgs.mkShell {
          packages = [ pkgs.python3 pkgs.python3Packages.setuptools ];
        };
      }
    ) // {
      # NixOS module
      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.hapticctl;
          hapticctl = self.packages.${pkgs.system}.hapticctl;
        in
        {
          options.services.hapticctl = {
            enable = lib.mkEnableOption "hapticctl haptic touchpad intensity restore service";

            device = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              example = "/dev/hidraw0";
              description = "HID device path. Auto-detected if null.";
            };

            defaultIntensity = lib.mkOption {
              type = lib.types.int;
              default = 50;
              description = "Intensity to set if no saved state exists (0-100).";
            };

            udevRules = lib.mkOption {
              type = lib.types.bool;
              default = true;
              description = "Install udev rules granting the 'input' group access to haptic HID devices.";
            };
          };

          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ hapticctl ];

            services.udev.extraRules = lib.mkIf cfg.udevRules ''
              KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{bInterfaceClass}=="03", GROUP="input", MODE="0660"
            '';

            systemd.services.hapticctl-restore = {
              description = "Restore haptic touchpad intensity";
              wantedBy = [ "multi-user.target" ];
              after = [ "systemd-udevd.service" ];
              serviceConfig = {
                Type = "oneshot";
                RemainAfterExit = true;
                ExecStart =
                  let
                    deviceArg = lib.optionalString (cfg.device != null) "--device ${cfg.device}";
                  in
                  "${hapticctl}/bin/hapticctl --system ${deviceArg} restore";
              };
            };

            # Write default intensity so restore has something to work with
            # if the user has never set one.
            system.activationScripts.hapticctl-default-state = lib.stringAfter [ "var" ] ''
              if [ ! -f /var/lib/hapticctl/intensity ]; then
                mkdir -p /var/lib/hapticctl
                echo ${toString cfg.defaultIntensity} > /var/lib/hapticctl/intensity
              fi
            '';
          };
        };
    };
}
