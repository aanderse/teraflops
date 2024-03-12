{ name, config, pkgs, lib, ... }: with lib;
let
  # sourced from https://github.com/NixOS/nixpkgs/pull/258250
  net = (import ./net.nix { inherit lib; });

  metadata = builtins.fromJSON resources.ssh_resource.${name}.result;
  public = head metadata.interfaces.public;
  private = head metadata.interfaces.private;
in
{
  # interface
  options.deployment.digitalocean = mkOption {
    type = with types; nullOr (submodule {
      freeformType = (pkgs.formats.json {}).type;
      options = {
        name = mkOption {
          type = types.str;
          default = name;
          description = ''
            The Droplet name.
          '';
        };

        image = mkOption {
          type = types.str;
          default = "ubuntu-22-04-x64";
          description = "The Droplet image ID or slug.";
        };

        region = mkOption {
          type = with types; nullOr str;
          example = "nyc2";
          description = ''
            The region where the Droplet will be created.
          '';
        };

        size = mkOption {
          type = types.str;
          example = "s-1vcpu-1gb";
          description = ''
            The unique slug that indentifies the type of Droplet. You can find a
            list of available slugs on [DigitalOcean API documentation](https://docs.digitalocean.com/reference/api/api-reference/#tag/Sizes).
          '';
        };

        ipv6 = mkOption {
          type = types.bool;
          default = false;
          description = ''
            Boolean controlling if IPv6 is enabled.
          '';
        };
      };
    });
    default = null;
    description = ''
      `digitalocean_droplet` configuration, see [argument reference](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs/resources/droplet#argument-reference) for supported values.
    '';
  };

  options.fileSystems = let osConfig = config; in mkOption {
    type = with types; attrsOf (submodule ({ config, ... }: let fsConfig = config; in {
      options.digitalocean = mkOption {
        type = with types; nullOr (submodule ({ config, ... }: {
          freeformType = (pkgs.formats.json {}).type;
          options = {
            name = mkOption {
              type = types.str; # TODO: types.strMatching
              default = fsConfig.label;
              defaultText = literalExpression "fileSystems.<name>.label";
              description = ''
                A name for the block storage volume. Must be lowercase and be composed only of numbers, letters and "-", up to a limit of 64 characters. The name must begin with a letter.
              '';
            };

            region = mkOption {
              type = types.str;
              default = osConfig.deployment.digitalocean.region;
              defaultText = literalExpression "config.deployment.digitalocean.region";
              description = ''
                The region that the block storage volume will be created in.
              '';
            };

            size = mkOption {
              type = types.ints.unsigned;
              description = ''
                The size of the block storage volume in GiB. If updated, can only be expanded.
              '';
            };

            initial_filesystem_label = mkOption {
              type = with types; nullOr str;
              default = fsConfig.label;
              defaultText = literalExpression "fileSystems.<name>.label";
              description = "Initial filesystem label for the block storage volume.";
            };

            initial_filesystem_type = mkOption {
              type = types.enum [ "ext4" "xfs" ];
              default = fsConfig.fsType;
              defaultText = literalExpression "fileSystems.<name>.fsType";
              description = "Initial filesystem type for the block storage volume.";
            };
          };
        }));
        default = null;
        description = ''
          Provides a DigitalOcean Block Storage volume attached to this Droplet in order to provide expanded storage.
        '';
      };

      config = mkIf (config.digitalocean != null) {
        autoFormat = true;
        autoResize = true;
      };
    }));
  };

  # implementation
  config = mkIf (config.deployment.targetEnv == "digitalocean") {
    assertions = mapAttrsToList (mountPoint: fs: {
      assertion = fs.digitalocean != null -> fs.label != null;
      message = "you must set a label on ${name}.fileSystems.${mountPoint}";
    }) config.fileSystems;

    deployment.targetHost =
      let
        attribute = if config.deployment.digitalocean.ipv6 then "ipv6_address" else "ipv4_address";
      in
        if resources != null
          then resources.digitalocean_droplet.${name}.${attribute}
          else tf.ref "digitalocean_droplet.${name}.${attribute}";

    boot.loader.grub.device = "/dev/vda";

    fileSystems."/" = {
      fsType = "ext4";
      device = "/dev/vda1";
      autoResize = mkDefault true;
    };

    networking.nameservers = metadata.dns.nameservers;
    networking.defaultGateway = public.ipv4.gateway;

    # TODO: ipv6 support
    # TODO: include floating and reserved ip addresses
    networking.interfaces.eth0.ipv4 = {
      addresses = [
        { address = public.ipv4.ip_address; prefixLength = with net.ipv4; subnetMaskToBitMask (cidrToIpAddress public.ipv4.netmask); }
        { address = public.anchor_ipv4.ip_address; prefixLength = with net.ipv4; subnetMaskToBitMask (cidrToIpAddress public.anchor_ipv4.netmask); }
      ];
      routes = [
        { address = public.ipv4.gateway; prefixLength = 32; }
      ];
    };

    networking.interfaces.eth1 = {
      ipv4.addresses = [
        { address = private.ipv4.ip_address; prefixLength = with net.ipv4; subnetMaskToBitMask (cidrToIpAddress private.ipv4.netmask); }
      ];
    };

    services.udev.extraRules = ''
      ATTR{address}=="${public.mac}", NAME="eth0"
      ATTR{address}=="${private.mac}", NAME="eth1"
    '';

    services.do-agent.enable = mkDefault true;
    services.openssh.enable = true;

    users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
      resources.tls_private_key.teraflops.public_key_openssh
    ];

    # terraform: resource.digitalocean_droplet
    deployment.digitalocean = {
      # NOTE: droplets seem to insist on forcing password changes
      # if you use the usual cloud-init config for user provisioning
      user_data = mkIf config.deployment.provisionSSHKey ''
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
        port = mkIf (config.deployment.targetPort != null) config.deployment.targetPort;
        private_key = mkIf config.deployment.provisionSSHKey (tf.ref "tls_private_key.teraflops.private_key_openssh");
      };

      provisioner.remote-exec = {
        inline = [
          "curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | PROVIDER=digitalocean NIX_CHANNEL=nixos-23.11 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
          "shutdown -r +0"
        ];
      };
    };
  };
}
