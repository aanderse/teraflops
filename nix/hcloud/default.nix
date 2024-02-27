{ outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "hcloud") (outputs.teraflops.nodes or {});
in
{
  defaults = { modulesPath, name, config, pkgs, lib, ... }: with lib; {
    options.deployment.hcloud = mkOption {
      type = with types; nullOr (submodule {
        options = {

          location = mkOption {
            type = with types; nullOr (enum ["nbg1" "fsn1" "hel1" "ash" "hil"]);
            default = null;
            example = "nbg1";
            description = ''
              The ID of the location to create the server in.
            '';
          };

          name = mkOption {
            type = types.str;
            default = name;
            example = "custom-server-name";
            description = ''
              The Hetzner Cloud Server Instance `name`. This name
              must be unique within the scope of the Hetzner Cloud Project.
            '';
          };

          serverType = mkOption {
            type = types.str;
            default = "cx11";
            example = "cpx31";
            description = ''
              The Hetzner Cloud Server Instance type. A list of valid types can be
              found `here <https://www.hetzner.de/cloud#pricing>`_.
            '';
          };
        };
      });
      default = null;
    };

    config = mkIf (config.deployment.targetEnv == "hcloud") {
      deployment.hcloud = {};
      deployment.targetHost = if resources.exists
        then resources.hcloud_server.${name}.ipv4_address
        else resources.eval "hcloud_server.${name}.ipv4_address";

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
      hcloud_server = mapAttrs (name: node: with node.config; {
        name = deployment.hcloud.name;
        location = deployment.hcloud.location;

        image = "ubuntu-22.04";
        server_type = deployment.hcloud.serverType;

        user_data = mkIf node.config.deployment.provisionSSHKey ''
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
          user = deployment.targetUser;
          host = deployment.targetHost;
          port = mkIf (deployment.targetPort != null) deployment.targetPort;
          private_key = mkIf node.config.deployment.provisionSSHKey "\${tls_private_key.teraflops.public_key_openssh}";
        };

        provisioner.remote-exec = {
          inline = [
            "curl https://raw.githubusercontent.com/elitak/nixos-infect/master/nixos-infect | PROVIDER=hetznercloud NIX_CHANNEL=nixos-23.11 NO_REBOOT=true bash 2>&1 | tee /tmp/infect.log"
            "shutdown -r +0"
          ];
        };
      }) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/profiles/qemu-guest.nix" ];
}) nodes'
