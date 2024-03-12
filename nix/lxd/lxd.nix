{ name, config, pkgs, lib, ... }: with lib;
{
  # interface
  options.deployment.lxd = mkOption {
    type = with types; nullOr (submodule {
      freeformType = (pkgs.formats.json {}).type;
      options = {
        name = mkOption {
          type = types.str;
          default = name;
          description = "Name of the instance.";
        };

        image = mkOption {
          type = types.str;
          description = ''
            Base image from which the instance will be created. Must specify
            a NixOS image accessible from the provider remote.
          '';
        };
      };
    });
    default = null;
    description = ''
      `lxd_instance` configuration, see [argument reference](https://registry.terraform.io/providers/terraform-lxd/lxd/latest/docs/resources/instance#argument-reference) for supported values.
    '';
  };

  # implementation
  config = mkIf (config.deployment.targetEnv == "lxd") {
    deployment.targetHost = if resources != null
      then resources.lxd_instance.${config.deployment.lxd.name}.ipv6_address
      else tf.ref "lxd_instance.${config.deployment.lxd.name}.ipv6_address";

    services.openssh.enable = true;

    users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = optionals config.deployment.provisionSSHKey [
      resources.tls_private_key.teraflops.public_key_openssh
    ];

    # terraform: resource.lxd_instance
    deployment.lxd = {
      config = {
        "boot.autostart" = mkDefault true;
        "security.privileged" = mkDefault true;
      };

      file = mkIf config.deployment.provisionSSHKey [
        {
          content = tf.ref "tls_private_key.teraflops.public_key_openssh";
          target_path = "/root/.ssh/authorized_keys";
          mode = "0600";
          create_directories = true;
        }
      ];
    };
  };
}
