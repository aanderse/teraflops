{ outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "virtualbox") (outputs.teraflops.nodes or {});
in
{
  defaults = { modulesPath, name, config, pkgs, lib, ... }: with lib; {
    options.deployment.virtualbox = mkOption {
      type = with types; nullOr (submodule {
        options = {
          vcpu = mkOption {
            type = types.ints.unsigned;
            default = 2;
            description = ''
              The number of virtual CPUs.
            '';
          };

          memorySize = mkOption {
            type = types.str;
            default = "512 mib";
            description = ''
              Memory size of the virtual machine, allowing for human friend units like `mb`, `mib`, etc...
            '';
          };

          clientPublicKey = mkOption {
            type = types.str;
            description = ''
              SSH public key used to initially connect to the VM.
            '';
          };
        };
      });
      default = null;
    };

    config = mkIf (config.deployment.targetEnv == "virtualbox") {
      deployment.virtualbox = {};
      deployment.targetHost = if resources.exists
        then (head resources.virtualbox_vm.${name}.network_adapter).ipv4_address
        else resources.eval "element(virtualbox_vm.${name}.network_adapter, 0).ipv4_address";

      boot.vesa = false;
      boot.loader.timeout = 1;

      networking.hostName = name;

      services.openssh.enable = true;
      services.openssh.authorizedKeysFiles = [ ".vbox-nixops-client-key" ];

      # VirtualBox doesn't seem to lease IP addresses persistently, so we
      # may get a different IP address if dhcpcd is restarted.  So don't
      # restart dhcpcd.
      systemd.services.dhcpcd.restartIfChanged = false;
    };
  };

  terraform = {
    required_providers = {
      virtualbox = {
        source = "terra-farm/virtualbox";
        version = "0.2.2-alpha.1";
      };
    };
  };

  resource = { nodes, pkgs, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "virtualbox") nodes;

      ova = (import "${pkgs.path}/nixos/lib/eval-config.nix" {
        modules = [ ./virtualbox-image-nixops.nix ];
      }).config.system.build.virtualBoxOVA;
    in
    {
      # https://www.roksblog.de/terraform-virtualbox-provider-terrafarm/
      virtualbox_vm = mapAttrs (name: node: {
        inherit name;

        image = "${ova}/nixos-${node.config.system.nixos.version}-${node.config.nixpkgs.system}.ova";
        cpus = node.config.deployment.virtualbox.vcpu;
        memory = node.config.deployment.virtualbox.memorySize;

        network_adapter = {
          type           = "hostonly";
          host_interface = "vboxnet0";
        };

        provisioner.local-exec = {
          command = ''
            VBoxManage guestproperty set ''${self.id} /VirtualBox/GuestInfo/Charon/ClientPublicKey "${node.config.deployment.virtualbox.clientPublicKey}"
          '';
        };

        lifecycle = {
          ignore_changes = [
            "image"
          ];
        };
      }) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/virtualisation/virtualbox-image.nix" ];
}) nodes'
