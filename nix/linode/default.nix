{
  tf,
  outputs,
  resources,
  lib,
  ...
}:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "linode") (outputs.teraflops.nodes or { });
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
      options.deployment.linode = lib.mkOption {
        type = lib.types.nullOr (
          lib.types.submodule {
            freeformType = (pkgs.formats.json { }).type;
            options = {
              label = lib.mkOption {
                type = lib.types.str;
                default = name;
                description = ''
                  The Linode's label is for display purposes only.
                '';
              };

              type = lib.mkOption {
                type = lib.types.str;
                example = "g6-nanode-1";
                description = ''
                  The Linode type defines the pricing, CPU, disk, and RAM specs of the instance. See
                  all types [here](https://api.linode.com/v4/linode/types).
                '';
              };

              region = lib.mkOption {
                type = lib.types.str;
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
          }
        );
        default = null;
        description = ''
          `linode_instance` configuration, see [argument reference](https://registry.terraform.io/providers/linode/linode/latest/docs/resources/instance#argument-reference) for supported values.
        '';
      };

      options.fileSystems =
        let
          osConfig = config;
        in
        lib.mkOption {
          type = lib.types.attrsOf (
            lib.types.submodule (
              { config, ... }:
              let
                fsConfig = config;
              in
              {
                options.linode = lib.mkOption {
                  type = lib.types.nullOr (
                    lib.types.submodule {
                      freeformType = (pkgs.formats.json { }).type;
                      options = {
                        label = lib.mkOption {
                          type = lib.types.str;
                          default = fsConfig.label;
                          defaultText = lib.literalExpression "fileSystems.<name>.label";
                          description = ''
                            The label of the Linode Volume.
                          '';
                        };

                        region = lib.mkOption {
                          type = lib.types.str;
                          default = osConfig.deployment.linode.region;
                          defaultText = lib.literalExpression "config.deployment.linode.region";
                          description = ''
                            The region where this volume will be deployed.
                          '';
                        };

                        size = lib.mkOption {
                          type = lib.types.ints.between 10 10240;
                          description = ''
                            Size of the Volume in GB.
                          '';
                        };

                        linode_id = lib.mkOption {
                          internal = true;
                          default = tf.ref "linode_instance.${name}.id";
                        };
                      };
                    }
                  );
                  default = null;
                  description = ''
                    Provides a Linode Volume resource.
                  '';
                };

                config = lib.mkIf (config.linode != null) {
                  autoFormat = true;
                  autoResize = true;

                  device = resources.linode_volume.${config.linode.label}.filesystem_path;
                };
              }
            )
          );
        };

      config = lib.mkIf (config.deployment.targetEnv == "linode") {
        deployment.targetHost =
          if resources != null then
            resources.linode_instance.${name}.ip_address
          else
            tf.ref "linode_instance.${name}.ip_address";

        fileSystems."/" = {
          fsType = "ext4";
          label = "linode-root";
          device = lib.mkOverride 51 "/dev/disk/by-label/linode-root";
        };

        swapDevices = [
          { label = "linode-swap"; }
        ];

        # terraform: resource.linode_instance
        deployment.linode = {
          image = "linode/ubuntu22.04";

          authorized_keys = lib.optionals config.deployment.provisionSSHKey [
            (tf.ref "trimspace(tls_private_key.teraflops.public_key_openssh)")
          ];

          connection = {
            type = "ssh";
            user = config.deployment.targetUser;
            host = config.deployment.targetHost;
            port = lib.mkIf (config.deployment.targetPort != null) config.deployment.targetPort;
            private_key = lib.mkIf config.deployment.provisionSSHKey (
              tf.ref "tls_private_key.teraflops.private_key_openssh"
            );
          };

          provisioner.remote-exec = {
            inline = [
              "hostnamectl hostname nixos" # ensure 'networking.hostName' isn't "localhost"
              "curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | NIX_CHANNEL=nixos-24.05 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
              "shutdown -r +0"
            ];
          };
        };
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

  resource =
    {
      nodes,
      lib,
      ...
    }:
    let
      nodes' = lib.filterAttrs (_: node: node.config.deployment.targetEnv == "linode") nodes;
      data = lib.foldr (a: b: a // b) { } (lib.attrValues (lib.mapAttrs dataFn nodes'));
      dataFn =
        name: node:
        lib.mapAttrs' (_: fs: lib.nameValuePair fs.linode.label fs.linode) (
          lib.filterAttrs (_: fs: fs.linode != null) node.config.fileSystems
        );
    in
    {
      linode_instance = lib.mapAttrs (_: node: node.config.deployment.linode) nodes';
      linode_volume = data;
    };
}
// lib.mapAttrs (
  _: node:
  { modulesPath, ... }:
  {
    imports = [ "${modulesPath}/virtualisation/linode-config.nix" ];
  }
) nodes'
