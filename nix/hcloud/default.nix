{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "hcloud") (outputs.teraflops.nodes or {});
in
{
  defaults = { modulesPath, name, config, pkgs, lib, ... }: with lib; {
    options.deployment.hcloud = mkOption {
      type = with types; nullOr (submodule {
        freeformType = (pkgs.formats.json {}).type;
        options = {
          name = mkOption {
            type = types.strMatching "^$|^[[:alnum:]]([[:alnum:]_-]{0,61}[[:alnum:]])?$";
            default = name;
            description = ''
              Name of the server to create (must be unique per project and a valid hostname as per RFC 1123).
            '';
          };

          server_type = mkOption {
            type = types.str;
            example = "cpx31";
            description = ''
              Name of the server type this server should be created with.
            '';
          };
        };

        config = {
          image = "ubuntu-22.04";

          user_data = mkIf config.deployment.provisionSSHKey ''
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
            port = mkIf (config.deployment.targetPort != null) config.deployment.targetPort;
            private_key = mkIf config.deployment.provisionSSHKey (tf.ref "tls_private_key.teraflops.public_key_openssh");
          };

          provisioner.remote-exec = {
            inline = [
              "curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | PROVIDER=hetznercloud NIX_CHANNEL=nixos-23.11 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
              "shutdown -r +0"
            ];
          };
        };
      });
      default = null;
      description = ''
        `hcloud_server` configuration, see [argument reference](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs/resources/server#argument-reference) for supported values.
      '';
    };

    config = mkIf (config.deployment.targetEnv == "hcloud") {
      deployment.hcloud = {};
      deployment.targetHost = if resources != null
        then resources.hcloud_server.${name}.ipv4_address
        else tf.ref "hcloud_server.${name}.ipv4_address";

      boot.loader.grub.device = "/dev/sda";
      boot.initrd.kernelModules = [ "nvme" ];

      fileSystems."/" = {
        fsType = "ext4";
        device = "/dev/sda1";
      };

      networking.defaultGateway = "172.31.1.1";
      
      # TODO: hetzner cloud networking defaults, volumes, etc...

      services.openssh.enable = true;

      users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
        resources.tls_private_key.teraflops.public_key_openssh
      ];
    };
  };

  terraform = {
    required_providers = {
      hcloud = {
        source = "hetznercloud/hcloud";
        version = ">= 1.44.0";
      };
    };
  };

  resource = { nodes, pkgs, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "hcloud") nodes;
    in
    {
      hcloud_server = mapAttrs (_: node: node.config.deployment.hcloud) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/profiles/qemu-guest.nix" ];
}) nodes'
