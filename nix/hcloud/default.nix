{ config, tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "hcloud") (outputs.teraflops.nodes or {});
in
{
  defaults = { name, config, pkgs, lib, ... }:
  let
    osConfig = config;
    format = pkgs.formats.json { };
  in
  {
    options.deployment.hcloud = lib.mkOption {
      type = lib.types.nullOr (lib.types.submodule {
        freeformType = format.type;
        options = {
          name = lib.mkOption {
            type = lib.types.strMatching "^$|^[[:alnum:]]([[:alnum:]_-]{0,61}[[:alnum:]])?$";
            default = name;
            description = ''
              Name of the server to create (must be unique per project and a valid hostname as per RFC 1123).
            '';
          };

          server_type = lib.mkOption {
            type = lib.types.str;
            example = "cpx31";
            description = ''
              Name of the server type this server should be created with.
            '';
          };
        };
      });
      default = null;
      description = ''
        `hcloud_server` configuration, see [argument reference](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs/resources/server#argument-reference) for supported values.
      '';
    };

    options.fileSystems = let osConfig = config; in lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule ({ config, ... }: let fsConfig = config; in {
        options.hcloud = lib.mkOption {
          type = lib.types.nullOr (lib.types.submodule {
            freeformType = format.type;
            options = {
              name = lib.mkOption {
                type = lib.types.str;
                description = ''
                  Name of the volume to create (must be unique per project).
                '';
              };

              size = lib.mkOption {
                type = lib.types.ints.unsigned;
                description = ''
                  Size of the volume in GB.
                '';
              };

              location = lib.mkOption {
                type = lib.types.str;
                default = osConfig.deployment.hcloud.location;
                defaultText = lib.literalExpression "config.deployment.hcloud.location";
                description = ''
                  The location name of the volume to create. See the [Hetzner Docs](https://docs.hetzner.com/cloud/general/locations/#what-locations-are-there) for more details about locations.
                '';
              };

              automount = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = ''
                  Automount the volume upon attaching it.
                '';
              };

              format = lib.mkOption {
                type = lib.types.enum [ "ext4" "xfs" ];
                default = fsConfig.fsType;
                defaultText = lib.literalExpression "fileSystems.<name>.fsType";
                description = "Format volume after creation.";
              };
            };
          });
          default = null;
          description = ''
            Provides a Hetzner Cloud volume resource to manage volumes.
          '';
        };

        config = lib.mkIf (config.hcloud != null) {
          autoFormat = true;
          autoResize = true;

          device = resources.hcloud_volume.${config.hcloud.name}.linux_device;
        };
      }));
    };

    options.networking.interfaces = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options.ipv4.addresses = lib.mkOption {
          type = lib.types.listOf (lib.types.submodule ({ config, ... }: {
            options.hcloud = lib.mkOption {
              type = lib.types.nullOr (lib.types.submodule {
                freeformType = format.type;
                options = {
                  name = lib.mkOption {
                    type = lib.types.str;
                    description = ''
                      Name of the Floating IP.
                    '';
                  };

                  type = lib.mkOption {
                    type = lib.types.enum [ "ipv4" "ipv6" ];
                    default = "ipv4";
                    readOnly = true;
                    description = ''
                      Type of the Floating IP.
                    '';
                  };

                  home_location = lib.mkOption {
                    type = lib.types.str;
                    default = osConfig.deployment.hcloud.location;
                    defaultText = lib.literalExpression "config.deployment.hcloud.location";
                    description = ''
                      Name of home location (routing is optimized for that location).
                    '';
                  };
                };
              });
              default = null;
              description = ''
                Provides a Hetzner Cloud Floating IP to represent a publicly-accessible static IP address.
              '';
            };

            config = lib.mkIf (config.hcloud != null) {
              address = resources.hcloud_floating_ip.${config.hcloud.name}.ip_address;
              prefixLength = 32;
            };
          }));
        };

        options.ipv6.addresses = lib.mkOption {
          type = lib.types.listOf (lib.types.submodule ({ config, ... }: {
            options.hcloud = lib.mkOption {
              type = lib.types.nullOr (lib.types.submodule {
                freeformType = format.type;
                options = {
                  name = lib.mkOption {
                    type = lib.types.str;
                    description = ''
                      Name of the Floating IP.
                    '';
                  };

                  type = lib.mkOption {
                    type = lib.types.enum [ "ipv4" "ipv6" ];
                    default = "ipv6";
                    readOnly = true;
                    description = ''
                      Type of the Floating IP.
                    '';
                  };

                  home_location = lib.mkOption {
                    type = lib.types.str;
                    default = osConfig.deployment.hcloud.location;
                    defaultText = lib.literalExpression "config.deployment.hcloud.location";
                    description = ''
                      Name of home location (routing is optimized for that location).
                    '';
                  };
                };
              });
              default = null;
              description = ''
                Provides a Hetzner Cloud Floating IP to represent a publicly-accessible static IP address.
              '';
            };

            config = lib.mkIf (config.hcloud != null) {
              address = resources.hcloud_floating_ip.${config.hcloud.name}.ip_address;
              prefixLength = 64;
            };
          }));
        };
      });
    };

    config = lib.mkIf (config.deployment.targetEnv == "hcloud") {
      deployment.targetHost = if resources != null
        then resources.hcloud_server.${name}.ipv4_address
        else tf.ref "hcloud_server.${name}.ipv4_address";

      services.openssh.enable = true;

      # terraform: resource.hcloud_server
      deployment.hcloud = {
        image = "ubuntu-24.04";

        user_data = lib.mkIf config.deployment.provisionSSHKey ''
          #cloud-config
          users:
            - name: root
              lock_passwd: true
              ssh_authorized_keys:
                - ''${trimspace(tls_private_key.teraflops.public_key_openssh)}
          chpasswd:
            expire: false
        '';

        connection = {
          type = "ssh";
          user = config.deployment.targetUser;
          host = config.deployment.targetHost;
          port = lib.mkIf (config.deployment.targetPort != null) config.deployment.targetPort;
          private_key = lib.mkIf config.deployment.provisionSSHKey (tf.ref "tls_private_key.teraflops.private_key_openssh");
        };

        provisioner.remote-exec = {
          inline = [
            "curl https://raw.githubusercontent.com/elitak/nixos-infect/5ef3f953d32ab92405b280615718e0b80da2ebe6/nixos-infect | PROVIDER=hetznercloud NIX_CHANNEL=nixos-25.05 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
            "shutdown -r +0"
          ];
        };
      };
    };
  };

  terraform = {
    required_providers = {
      hcloud = {
        source = "hetznercloud/hcloud";
        version = ">= 1.44.0";
      };
      ssh = {
        source = "loafoe/ssh";
        version = ">= 2.7.0";
      };
    };
  };

  resource = { nodes, lib, ... }:
    let
      # generate a attrset of all nodes for hetzner to provision
      nodes' = lib.filterAttrs (_: node: node.config.deployment.targetEnv == "hcloud") nodes;

      # generate a list of all filesystems for hetzner to provision
      filesystems' = lib.flatten (
        lib.mapAttrsToList (name: node:
          lib.mapAttrsToList (k: v: {
            inherit (v) hcloud;
            server = name;
          })(lib.filterAttrs (_: v: v.hcloud or null != null) node.config.fileSystems)
        ) nodes'
      );

      # generate a list of all floating ip addresses for hetzner to provision
      addresses' = lib.flatten (
        lib.mapAttrsToList (name: node:
          lib.mapAttrsToList (_: v:
            lib.map (address: {
              inherit (address) hcloud;
              server = name;
            })(lib.filter (address: address.hcloud or null != null)(v.ipv4.addresses ++ v.ipv6.addresses))
          ) node.config.networking.interfaces
        ) nodes'
      );
    in
      lib.optionalAttrs (nodes' != { }) {
        hcloud_server = lib.mapAttrs (_: node: node.config.deployment.hcloud // {
          # NOTE: without ignoring these future versions of this provider could destroy existing nodes
          lifecycle.ignore_changes = [
            "image"
            "user_data"
          ];
        }) nodes';

        # NOTE: the hcloud terraform provider doesn't provide enough information to properly configure a node
        # so the extra data needed can be queried on the server during bootstrap and stored in terraform state
        #
        # system-info.sh will provide a list of modules to import on the associated node based on the work
        # done by nixos-infect.sh
        ssh_resource.teraflops = {
          for_each = tf.toMap (lib.mapAttrs (_: v: {
            # filter down to relevant options only to avoid bloating generated terraform json
            inherit (v.config.deployment)
              targetUser
              targetHost
              targetPort
              provisionSSHKey
            ;
          }) nodes');

          # NOTE: this ssh_resource should be used purely as a bootstrap step, not to be updated over time
          # therefore any changes to the script shouldn't cause the script to run again
          lifecycle.ignore_changes = [
            "file"
          ];

          user = tf.ref "each.value.targetUser";
          host = tf.ref "each.value.targetHost";
          port = tf.ref "each.value.targetPort";
          private_key = lib.mkIf (config.resource.tls_private_key.teraflops or null != null) (tf.ref "each.value.provisionSSHKey ? tls_private_key.teraflops.private_key_openssh : null");

          file = {
            source = ./system-info.sh;
            destination = "/run/system-info.sh";
            permissions = "0755";
          };

          commands = [
            "/run/system-info.sh"
          ];

          # since `depends_on` requires a static value unfortunately we are forced to
          # depend on all nodes being provisioned before we can start querying via ssh
          depends_on = lib.mapAttrsToList (name: _: "hcloud_server.${name}") nodes';
        };
      } // lib.optionalAttrs (filesystems' != [ ]) {
        hcloud_volume = lib.genAttrs' filesystems' (data: lib.nameValuePair data.hcloud.name (builtins.removeAttrs data.hcloud ["automount"]));
        hcloud_volume_attachment = lib.genAttrs' filesystems' (data: lib.nameValuePair "${data.hcloud.name}-on-${data.server}" {
          server_id = tf.ref "hcloud_server.${data.server}.id";
          volume_id = tf.ref "hcloud_volume.${data.hcloud.name}.id";

          inherit (data.hcloud) automount;
        });
      } // lib.optionalAttrs (addresses' != [ ]) {
        hcloud_floating_ip = lib.genAttrs' addresses' (v: lib.nameValuePair v.hcloud.name v.hcloud);
        hcloud_floating_ip_assignment = lib.genAttrs' addresses' (v: lib.nameValuePair "${v.hcloud.name}-on-${v.server}" {
          floating_ip_id = tf.ref "hcloud_floating_ip.${v.hcloud.name}.id";
          server_id = tf.ref "hcloud_server.${v.server}.id";
        });
      };
} // lib.mapAttrs (name: node: { modulesPath, ... }: {
  imports = [
    (modulesPath + "/profiles/qemu-guest.nix")
    (modulesPath + "/profiles/minimal.nix")
  ] ++ builtins.fromJSON (resources.ssh_resource.teraflops.${name}.result or "[]");
}) nodes'
