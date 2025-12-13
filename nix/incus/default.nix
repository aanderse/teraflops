{
  tf,
  outputs,
  resources,
  lib,
  ...
}:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "incus") (outputs.teraflops.nodes or { });
in
{
  defaults =
    {
      name,
      config,
      pkgs,
      lib,
      ...
    }:
    {
      options.deployment.incus = lib.mkOption {
        type = lib.types.nullOr (
          lib.types.submodule {
            freeformType = (pkgs.formats.json { }).type;
            options = {
              name = lib.mkOption {
                type = lib.types.str;
                default = name;
                description = "Name of the instance.";
              };

              image = lib.mkOption {
                type = lib.types.str;
                default = "images:nixos/unstable";
                description = ''
                  Base image from which the instance will be created. Must specify
                  a NixOS image accessible from the provider remote.
                '';
              };
            };
          }
        );
        default = null;
        description = ''
          `incus_instance` configuration, see [argument reference](https://registry.terraform.io/providers/lxc/incus/latest/docs/resources/instance#argument-reference) for supported values.
        '';
      };

      config = lib.mkIf (config.deployment.targetEnv == "incus") {
        deployment.targetHost =
          if resources != null then
            resources.incus_instance.${config.deployment.incus.name}.ipv6_address
          else
            tf.ref "incus_instance.${config.deployment.incus.name}.ipv6_address";

        services.openssh.enable = true;

        # terraform: resource.incus_instance
        deployment.incus = {
          config = {
            "boot.autostart" = lib.mkDefault true;
            "security.privileged" = lib.mkDefault true;
          };

          file = lib.mkIf config.deployment.provisionSSHKey [
            {
              content = tf.ref "tls_private_key.teraflops.public_key_openssh";
              target_path = "/root/.ssh/authorized_keys";
              mode = "0600";
              create_directories = true;
            }
          ];
        };
      };
    };

  terraform = {
    required_providers = {
      incus = {
        source = "lxc/incus";
        version = ">= 0.1.0";
      };
    };
  };

  resource =
    {
      nodes,
      lib,
      ...
    }:
    let
      nodes' = lib.filterAttrs (_: node: node.config.deployment.targetEnv == "incus") nodes;
    in
    {
      incus_instance = lib.mapAttrs (_: node: node.config.deployment.incus) nodes';
    };
}
// lib.mapAttrs (
  _: node:
  { modulesPath, ... }:
  {
    imports = [ "${modulesPath}/virtualisation/lxc-container.nix" ];
  }
) nodes'
