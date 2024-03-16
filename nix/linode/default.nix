{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "linode") (outputs.teraflops.nodes or {});
in
{
  defaults = { modulesPath, name, config, pkgs, lib, ... }: with lib; {
    options.deployment.linode = mkOption {
      type = with types; nullOr (submodule {
        freeformType = (pkgs.formats.json {}).type;
        options = {
          label = mkOption {
            type = types.str;
            default = name;
            description = ''
              The Linode's label is for display purposes only.
            '';
          };

          type = mkOption {
            type = types.str;
            example = "g6-nanode-1";
            description = ''
              The Linode type defines the pricing, CPU, disk, and RAM specs of the instance. See
              all types [here](https://api.linode.com/v4/linode/types).
            '';
          };

          region = mkOption {
            type = types.str;
            example = "us-east";
            description = ''
              This is the location where the Linode is deployed. See all regions
              [here](https://api.linode.com/v4/regions). Changing region will trigger a migration
              of this Linode. Migration operations are typically long-running operations, so the
              [update timeout](https://registry.terraform.io/providers/linode/linode/latest/docs/resources/instance#timeouts)
              should be adjusted accordingly.
            '';
          };
        };

        config = {
          image = "linode/ubuntu22.04";

          authorized_keys = optionals config.deployment.provisionSSHKey [
            (tf.ref "trimspace(tls_private_key.teraflops.public_key_openssh)")
          ];

          connection = {
            type = "ssh";
            user = config.deployment.targetUser;
            host = config.deployment.targetHost;
            port = mkIf (config.deployment.targetPort != null) config.deployment.targetPort;
            private_key = mkIf config.deployment.provisionSSHKey (tf.ref "tls_private_key.teraflops.private_key_openssh");
          };

          provisioner.remote-exec = {
            inline = [
              "hostnamectl hostname nixos" # ensure 'networking.hostName' isn't "localhost"
              "curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | NIX_CHANNEL=nixos-23.11 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
              "shutdown -r +0"
            ];
          };
        };
      });
      default = null;
      description = ''
        `linode_instance` configuration, see [argument reference](https://registry.terraform.io/providers/linode/linode/latest/docs/resources/instance#argument-reference) for supported values.
      '';
    };

    options.fileSystems = let osConfig = config; in mkOption {
      type = with types; attrsOf (submodule ({ config, ... }: let fsConfig = config; in {
        options.linode = mkOption {
          type = with types; nullOr (submodule ({ config, ... }: {
            freeformType = (pkgs.formats.json {}).type;
            options = {
              label = mkOption {
                type = types.str;
                default = fsConfig.label;
                defaultText = literalExpression "fileSystems.<name>.label";
                description = ''
                  The label of the Linode Volume.
                '';
              };

              region = mkOption {
                type = types.str;
                default = osConfig.deployment.linode.region;
                defaultText = literalExpression "config.deployment.linode.region";
                description = ''
                  The region where this volume will be deployed.
                '';
              };

              size = mkOption {
                type = types.ints.between 10 10240;
                description = ''
                  Size of the Volume in GB.
                '';
              };

              linode_id = mkOption {
                internal = true;
                default = tf.ref "linode_instance.${name}.id";
              };
            };
          }));
          default = null;
          description = ''
            Provides a Linode Volume resource.
          '';
        };

        config = mkIf (config.linode != null) {
          autoFormat = true;
          autoResize = true;

          device = resources.linode_volume.${config.linode.label}.filesystem_path;
        };
      }));
    };

    config = mkIf (config.deployment.targetEnv == "linode") {
      deployment.linode = {};
      deployment.targetHost = if resources != null
        then resources.linode_instance.${name}.ip_address
        else tf.ref "linode_instance.${name}.ip_address";

      boot.kernelParams = [ "console=ttyS0,19200n8" ];
      boot.loader.grub.device = "nodev";
      boot.loader.grub.extraConfig = ''
        serial --speed=19200 --unit=0 --word=8 --parity=no --stop=1;
        terminal_input serial;
        terminal_output serial
      '';

      # TODO: linode provides some useful data that could be used to set 'fileSystems' and 'swapDevices'
      fileSystems."/" = {
        fsType = "ext4";
        device = "/dev/sda";
      };

      swapDevices = [
        { device = "/dev/sdb"; }
      ];

      services.openssh.enable = true;

      users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
        resources.tls_private_key.teraflops.public_key_openssh
      ];
    };
  };

  terraform = {
    required_providers = {
      linode = {
        source = "linode/linode";
        version = ">= 2.13.0";
      };
    };
  };

  resource = { nodes, pkgs, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "linode") nodes;
      data = foldr (a: b: a // b) {} (attrValues (mapAttrs dataFn nodes'));
      dataFn = name: node: mapAttrs' (_: fs: nameValuePair fs.linode.label fs.linode) (filterAttrs (_: fs: fs.linode != null) node.config.fileSystems);
    in
    {
      linode_instance = mapAttrs (_: node: node.config.deployment.linode) nodes';
      linode_volume = data;
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/profiles/qemu-guest.nix" ];
}) nodes'
