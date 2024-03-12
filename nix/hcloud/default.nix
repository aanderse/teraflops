{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "hcloud") (outputs.teraflops.nodes or {});
in
{
  defaults = {
    imports = [ ./hcloud.nix ];
  };

  terraform = {
    required_providers = {
      hcloud = {
        source = "hetznercloud/hcloud";
        version = ">= 1.44.0";
      };
    };
  };

  resource = { nodes, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "hcloud") nodes;
    in
    {
      hcloud_server = mapAttrs (_: node: node.config.deployment.hcloud) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/profiles/qemu-guest.nix" ];
}) nodes'
