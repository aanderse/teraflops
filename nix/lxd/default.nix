{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "lxd") (outputs.teraflops.nodes or {});
in
{
  defaults = {
    imports = [ ./lxd.nix ];
  };

  terraform = {
    required_providers = {
      lxd = {
        source = "terraform-lxd/lxd";
        version = ">= 2.0.0";
      };
    };
  };

  resource = { nodes, pkgs, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "lxd") nodes;
    in
    {
      lxd_instance = mapAttrs (_: node: node.config.deployment.lxd) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/virtualisation/lxc-container.nix" ];
}) nodes'
