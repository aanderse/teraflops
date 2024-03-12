{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "virtualbox") (outputs.teraflops.nodes or {});
in
{
  defaults = {
    imports = [ ./virtualbox.nix ];
  };

  terraform = {
    required_providers = {
      virtualbox = {
        source = "terra-farm/virtualbox";
        version = "0.2.2-alpha.1";
      };
    };
  };

  resource = { nodes, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "virtualbox") nodes;
    in
    {
      virtualbox_vm = mapAttrs (_: node: node.config.deployment.virtualbox) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/virtualisation/virtualbox-image.nix" ];
}) nodes'
