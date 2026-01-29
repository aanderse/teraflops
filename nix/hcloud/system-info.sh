#! /usr/bin/env nix-shell
#! nix-shell -i bash -p jq

set -euo pipefail

# evaluate the data gathering that nixos-infect has done as a list of inline nixos configurations
configuration=$( nix --extra-experimental-features nix-command eval --impure --raw --expr 'builtins.toJSON (builtins.removeAttrs (import /etc/nixos/configuration.nix { }) ["imports"])' | jq 'del(.users.users.root.openssh.authorizedKeys.keys)' )
hardware_configuration=$( nix --extra-experimental-features nix-command eval --impure --raw --expr 'builtins.toJSON (builtins.removeAttrs (import /etc/nixos/hardware-configuration.nix { modulesPath = <nixpkgs/nixos/modules>; }) ["imports"])' )
networking=$( nix --extra-experimental-features nix-command eval --impure --raw --expr 'builtins.toJSON (builtins.removeAttrs (import /etc/nixos/networking.nix { lib = import <nixpkgs/lib>; }) ["imports"])' )

echo "[ $configuration, $hardware_configuration, $networking ]"
