# adapted from https://github.com/nix-community/nixops-vbox/blob/master/nixopsvbox/nix/virtualbox-image-nixops.nix
{ modulesPath, config, ... }:
let
  clientKeyPath = "/root/.vbox-nixops-client-key";
  clientPublicKey = "/VirtualBox/GuestInfo/Charon/ClientPublicKey";
in
{
  imports = [ "${modulesPath}/virtualisation/virtualbox-image.nix" ];

  boot.vesa = false;
  boot.loader.timeout = 1;

  services.openssh.enable = true;
  services.openssh.authorizedKeysFiles = [ ".vbox-nixops-client-key" ];

  # VirtualBox doesn't seem to lease IP addresses persistently, so we
  # may get a different IP address if dhcpcd is restarted.  So don't
  # restart dhcpcd.
  systemd.services.dhcpcd.restartIfChanged = false;

  systemd.services.get-vbox-nixops-client-key = {
    description = "Get NixOps SSH Key";
    wantedBy = [ "multi-user.target" ];
    before = [ "sshd.service" ];
    requires = [ "dev-vboxguest.device" ];
    after = [ "dev-vboxguest.device" ];
    path = [ config.boot.kernelPackages.virtualboxGuestAdditions ];
    script = ''
      while VBoxControl -nologo guestproperty get ${clientPublicKey} | grep --quiet 'No value set!'; do
        sleep 5s
      done

      set -o pipefail

      VBoxControl -nologo guestproperty get ${clientPublicKey} | sed 's/Value: //' > ${clientKeyPath}.tmp
      mv ${clientKeyPath}.tmp ${clientKeyPath}
    '';
    serviceConfig.TimeoutStartSec = "90s";
  };

  # bootstrap image - suppress superfluous warning
  system.stateVersion = config.system.nixos.release;
}
