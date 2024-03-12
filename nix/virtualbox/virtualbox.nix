{ name, config, pkgs, lib, ... }: with lib;
{
  # interface
  options.deployment.virtualbox = mkOption {
    type = with types; nullOr (submodule {
      freeformType = (pkgs.formats.json {}).type;
      options = {
        name = mkOption {
          type = types.str;
          default = name;
          description = "The name of the virtual machine.";
        };
      };
    });
    default = null;
    description = ''
      `virtualbox_vm` configuration, see [argument reference](https://registry.terraform.io/providers/terra-farm/virtualbox/latest/docs/resources/vm#argument-reference) for supported values.
    '';
  };

  # implementation
  config = mkIf (config.deployment.targetEnv == "virtualbox") {
    deployment.targetHost = if resources != null
      then (head resources.virtualbox_vm.${name}.network_adapter).ipv4_address
      else tf.ref "element(virtualbox_vm.${name}.network_adapter, 0).ipv4_address";

    boot.vesa = false;
    boot.loader.timeout = 1;

    services.openssh.enable = true;
    services.openssh.authorizedKeysFiles = [ ".vbox-nixops-client-key" ];

    users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
      resources.tls_private_key.teraflops.public_key_openssh
    ];

    # VirtualBox doesn't seem to lease IP addresses persistently, so we
    # may get a different IP address if dhcpcd is restarted.  So don't
    # restart dhcpcd.
    systemd.services.dhcpcd.restartIfChanged = false;

    # terraform: resource.virtualbox_vm
    deployment.virtualbox = {
      image =
        let
          ova = (import "${pkgs.path}/nixos/lib/eval-config.nix" {
            modules = [ ./virtualbox-image-nixops.nix ];
          }).config.system.build.virtualBoxOVA;
        in
          "${ova}/nixos-${config.system.nixos.version}-${config.nixpkgs.system}.ova";

      # https://www.roksblog.de/terraform-virtualbox-provider-terrafarm/
      network_adapter = {
        type = "hostonly";
        host_interface = "vboxnet0";
      };

      provisioner = mkIf config.deployment.provisionSSHKey {
        local-exec = {
          command = ''
            VBoxManage guestproperty set ''${self.id} /VirtualBox/GuestInfo/Charon/ClientPublicKey "''${trimspace(tls_private_key.teraflops.public_key_openssh)}"
          '';
        };
      };

      lifecycle = {
        ignore_changes = [
          # image depends on pkgs which will change
          "image"
        ];
      };
    };
  };
}
