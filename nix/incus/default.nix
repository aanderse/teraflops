{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "incus") (outputs.teraflops.nodes or {});
in
{
  defaults = { name, config, pkgs, lib, ... }: with lib; {
    options.deployment.incus = mkOption {
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
            default = "images:nixos/unstable";
            description = ''
              Base image from which the instance will be created. Must specify
              a NixOS image accessible from the provider remote.
            '';
          };
        };
      });
      default = null;
      description = ''
        `incus_instance` configuration, see [argument reference](https://registry.terraform.io/providers/lxc/incus/latest/docs/resources/instance#argument-reference) for supported values.
      '';
    };

    config = mkIf (config.deployment.targetEnv == "incus") {
      deployment.targetHost = if resources != null
        then resources.incus_instance.${config.deployment.incus.name}.ipv6_address
        else tf.ref "incus_instance.${config.deployment.incus.name}.ipv6_address";

      services.openssh.enable = true;

      users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
        resources.tls_private_key.teraflops.public_key_openssh
      ];

      # terraform: resource.incus_instance
      deployment.incus = {
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

  resource = { nodes, pkgs, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "incus") nodes;
    in
    {
      incus_instance = mapAttrs (_: node: node.config.deployment.incus) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/virtualisation/lxc-container.nix" ];
}) nodes'
