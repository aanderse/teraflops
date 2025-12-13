{
  tf,
  outputs,
  resources,
  lib,
  ...
}:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "lxd") (outputs.teraflops.nodes or { });
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
      options.deployment.lxd = lib.mkOption {
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
          `lxd_instance` configuration, see [argument reference](https://registry.terraform.io/providers/terraform-lxd/lxd/latest/docs/resources/instance#argument-reference) for supported values.
        '';
      };

      config = lib.mkIf (config.deployment.targetEnv == "lxd") {
        deployment.targetHost =
          if resources != null then
            resources.lxd_instance.${config.deployment.lxd.name}.ipv6_address
          else
            tf.ref "lxd_instance.${config.deployment.lxd.name}.ipv6_address";

        services.openssh.enable = true;

        # terraform: resource.lxd_instance
        deployment.lxd = {
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
      lxd = {
        source = "terraform-lxd/lxd";
        version = ">= 2.0.0";
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
      nodes' = lib.filterAttrs (_: node: node.config.deployment.targetEnv == "lxd") nodes;
    in
    {
      lxd_instance = lib.mapAttrs (_: node: node.config.deployment.lxd) nodes';
    };
}
// lib.mapAttrs (
  _: node:
  { modulesPath, ... }:
  {
    imports = [ "${modulesPath}/virtualisation/lxc-container.nix" ];
  }
) nodes'
