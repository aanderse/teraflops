{
  tf,
  outputs,
  resources,
  lib,
  ...
}:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "digitalocean") (
    outputs.teraflops.nodes or { }
  );
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
      options.deployment.digitalocean = lib.mkOption {
        type = lib.types.nullOr (
          lib.types.submodule {
            freeformType = (pkgs.formats.json { }).type;
            options = {
              name = lib.mkOption {
                type = lib.types.str;
                default = name;
                description = ''
                  The Droplet name.
                '';
              };

              image = lib.mkOption {
                type = lib.types.str;
                default = "ubuntu-22-04-x64";
                description = "The Droplet image ID or slug.";
              };

              region = lib.mkOption {
                type = with lib.types; nullOr str;
                example = "nyc2";
                description = ''
                  The region where the Droplet will be created.
                '';
              };

              size = lib.mkOption {
                type = lib.types.str;
                example = "s-1vcpu-1gb";
                description = ''
                  The unique slug that indentifies the type of Droplet. You can find a
                  list of available slugs on [DigitalOcean API documentation](https://docs.digitalocean.com/reference/api/api-reference/#tag/Sizes).
                '';
              };

              ipv6 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = ''
                  Boolean controlling if IPv6 is enabled.
                '';
              };
            };
          }
        );
        default = null;
        description = ''
          `digitalocean_droplet` configuration, see [argument reference](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/droplet#argument-reference) for supported values.
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
                options.digitalocean = lib.mkOption {
                  type = lib.types.nullOr (
                    lib.types.submodule {
                      freeformType = (pkgs.formats.json { }).type;
                      options = {
                        name = lib.mkOption {
                          # TODO: types.strMatching
                          type = lib.types.str;
                          default = fsConfig.label;
                          defaultText = lib.literalExpression "fileSystems.<name>.label";
                          description = ''
                            A name for the block storage volume. Must be lowercase and be composed only of numbers, letters and "-", up to a limit of 64 characters. The name must begin with a letter.
                          '';
                        };

                        region = lib.mkOption {
                          type = lib.types.str;
                          default = osConfig.deployment.digitalocean.region;
                          defaultText = lib.literalExpression "config.deployment.digitalocean.region";
                          description = ''
                            The region that the block storage volume will be created in.
                          '';
                        };

                        size = lib.mkOption {
                          type = lib.types.ints.unsigned;
                          description = ''
                            The size of the block storage volume in GiB. If updated, can only be expanded.
                          '';
                        };

                        initial_filesystem_label = lib.mkOption {
                          type = with lib.types; nullOr str;
                          default = fsConfig.label;
                          defaultText = lib.literalExpression "fileSystems.<name>.label";
                          description = "Initial filesystem label for the block storage volume.";
                        };

                        initial_filesystem_type = lib.mkOption {
                          type = lib.types.enum [
                            "ext4"
                            "xfs"
                          ];
                          default = fsConfig.fsType;
                          defaultText = lib.literalExpression "fileSystems.<name>.fsType";
                          description = "Initial filesystem type for the block storage volume.";
                        };
                      };
                    }
                  );
                  default = null;
                  description = ''
                    Provides a DigitalOcean Block Storage volume attached to this Droplet in order to provide expanded storage.
                  '';
                };

                config = lib.mkIf (config.digitalocean != null) {
                  autoFormat = true;
                  autoResize = true;
                };
              }
            )
          );
        };

      config =
        let
          # sourced from https://github.com/NixOS/nixpkgs/pull/258250
          net = import ./net.nix { inherit lib; };

          metadata = builtins.fromJSON resources.ssh_resource.${name}.result;
          public = lib.head metadata.interfaces.public;
          private = lib.head metadata.interfaces.private;
        in
        lib.mkIf (config.deployment.targetEnv == "digitalocean") {
          assertions = lib.mapAttrsToList (mountPoint: fs: {
            assertion = fs.digitalocean != null -> fs.label != null;
            message = "you must set a label on ${name}.fileSystems.${mountPoint}";
          }) config.fileSystems;

          deployment.targetHost =
            let
              attribute = if config.deployment.digitalocean.ipv6 then "ipv6_address" else "ipv4_address";
            in
            if resources != null then
              resources.digitalocean_droplet.${name}.${attribute}
            else
              tf.ref "digitalocean_droplet.${name}.${attribute}";

          boot.loader.grub.device = "/dev/vda";

          fileSystems."/" = {
            fsType = "ext4";
            device = "/dev/vda1";
            autoResize = lib.mkDefault true;
          };

          networking.nameservers = metadata.dns.nameservers;
          networking.defaultGateway = public.ipv4.gateway;

          # TODO: ipv6 support
          # TODO: include floating and reserved ip addresses
          networking.interfaces.eth0.ipv4 = {
            addresses = [
              {
                address = public.ipv4.ip_address;
                prefixLength = with net.ipv4; subnetMaskToBitMask (cidrToIpAddress public.ipv4.netmask);
              }
              {
                address = public.anchor_ipv4.ip_address;
                prefixLength = with net.ipv4; subnetMaskToBitMask (cidrToIpAddress public.anchor_ipv4.netmask);
              }
            ];
            routes = [
              {
                address = public.ipv4.gateway;
                prefixLength = 32;
              }
            ];
          };

          networking.interfaces.eth1 = {
            ipv4.addresses = [
              {
                address = private.ipv4.ip_address;
                prefixLength = with net.ipv4; subnetMaskToBitMask (cidrToIpAddress private.ipv4.netmask);
              }
            ];
          };

          services.udev.extraRules = ''
            ATTR{address}=="${public.mac}", NAME="eth0"
            ATTR{address}=="${private.mac}", NAME="eth1"
          '';

          services.do-agent.enable = lib.mkDefault true;
          services.openssh.enable = true;

          # terraform: resource.digitalocean_droplet
          deployment.digitalocean = {
            # NOTE: droplets seem to insist on forcing password changes
            # if you use the usual cloud-init config for user provisioning
            user_data = lib.mkIf config.deployment.provisionSSHKey ''
              #cloud-config
              runcmd:
                - chage -I -1 -m 0 -M 99999 -E -1 -d -1 root
                - mkdir -m 0700 /root/.ssh
                - echo "''${trimspace(tls_private_key.teraflops.public_key_openssh)}" > /root/.ssh/authorized_keys
            '';

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
                "curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | PROVIDER=digitalocean NIX_CHANNEL=nixos-24.05 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
                "shutdown -r +0"
              ];
            };
          };
        };
    };

  terraform = {
    required_providers = {
      digitalocean = {
        source = "digitalocean/digitalocean";
        version = ">= 2.32.0";
      };
      ssh = {
        source = "loafoe/ssh";
        version = ">= 2.7.0";
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
      nodes' = lib.filterAttrs (_: node: node.config.deployment.targetEnv == "digitalocean") nodes;
      data = lib.foldr (a: b: a // b) { } (lib.attrValues (lib.mapAttrs dataFn nodes'));
      dataFn =
        name: node:
        lib.mapAttrs' (
          _: fs:
          lib.nameValuePair fs.digitalocean.name {
            inherit (fs) digitalocean;

            droplet = name;
          }
        ) (lib.filterAttrs (_: fs: fs.digitalocean != null) node.config.fileSystems);
    in
    {
      digitalocean_droplet = lib.mapAttrs (_: node: node.config.deployment.digitalocean) nodes';

      digitalocean_volume = lib.mapAttrs (_: data: data.digitalocean) data;
      digitalocean_volume_attachment = lib.mapAttrs' (
        name: data:
        lib.nameValuePair "${name}-on-${data.droplet}" {
          droplet_id = tf.ref "digitalocean_droplet.${data.droplet}.id";
          volume_id = tf.ref "digitalocean_volume.${name}.id";
        }
      ) data;

      # HACK: account for an incomplete terraform provider
      #
      # it should be relatively easy to extend the existing terraform provider to
      # include this information
      #
      # see https://github.com/digitalocean/terraform-provider-digitalocean/issues/1097
      ssh_resource = lib.mapAttrs (name: node: {
        user = node.config.deployment.targetUser;
        host = node.config.deployment.targetHost;
        port = lib.mkIf (node.config.deployment.targetPort != null) node.config.deployment.targetPort;
        private_key = lib.mkIf node.config.deployment.provisionSSHKey (
          tf.ref "tls_private_key.teraflops.private_key_openssh"
        );

        commands = [
          "curl -fsSL http://169.254.169.254/metadata/v1.json"
        ];

        depends_on = [
          "digitalocean_droplet.${name}"
        ];
      }) nodes';
    };
}
// lib.mapAttrs (
  _: node:
  { modulesPath, ... }:
  {
    imports = [ "${modulesPath}/profiles/qemu-guest.nix" ];
  }
) nodes'
