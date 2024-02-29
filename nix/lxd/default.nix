{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "lxd") (outputs.teraflops.nodes or {});
in
{
  defaults = { name, config, pkgs, lib, ... }: with lib; {
    options.deployment.lxd = mkOption {
      type = with types; nullOr (submodule {
        freeformType = (pkgs.formats.json {}).type;
        options = {
          name = mkOption {
            type = types.str;
            default = name;
            description = "Name of the instance.";
          };

          image = mkOption {
            type = types.str;
            description = ''
              Base image from which the instance will be created. Must specify
              a NixOS image accessible from the provider remote.
            '';
          };
        };

        config = {
          config = {
            "boot.autostart" = mkDefault true;
            "security.privileged" = mkDefault true;
          };

          file = mkIf config.deployment.provisionSSHKey [
            {
              content = tf.ref "tls_private_key.teraflops.public_key_openssh";
              target_path = "/root/.ssh/authorized_keys";
              mode = "0600";
              create_directories = true;
            }
          ];
        };
      });
      default = null;
      description = ''
        `lxd_instance` configuration, see [argument reference](https://registry.terraform.io/providers/terraform-lxd/lxd/latest/docs/resources/instance#argument-reference) for supported values.
      '';
    };

    config = mkIf (config.deployment.targetEnv == "lxd") {
      deployment.lxd = {};
      deployment.targetHost = if resources != null
        then resources.lxd_instance.${config.deployment.lxd.name}.ipv6_address
        else tf.ref "lxd_instance.${config.deployment.lxd.name}.ipv6_address";

      services.openssh.enable = true;

      users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
        resources.tls_private_key.teraflops.public_key_openssh
      ];
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
