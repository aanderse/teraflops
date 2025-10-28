#! /usr/bin/env nix-shell
#! nix-shell -i bash -p jq

set -euo pipefail

# evaluate the data gathering that nixos-infect has done as a list of inline nixos configurations
configuration=$( nix-instantiate --eval -E 'let expr = import /etc/nixos/configuration.nix { }; in builtins.toJSON (builtins.removeAttrs expr ["imports"])' | jq '.' -r | jq 'del(.users.users.root.openssh.authorizedKeys.keys)' )
hardware_configuration=$( nix-instantiate --eval -E 'let expr = import /etc/nixos/hardware-configuration.nix { modulesPath = <nixpkgs/nixos/modules>; }; in builtins.toJSON (builtins.removeAttrs expr ["imports"])' | jq '.' -r | jq '.' )
networking=$( nix-instantiate --eval -E 'let expr = import /etc/nixos/networking.nix { lib = import <nixpkgs/lib>; }; in builtins.toJSON (builtins.removeAttrs expr ["imports"])' | jq '.' -r | jq '.' )

echo "[ $configuration, $hardware_configuration, $networking ]"
