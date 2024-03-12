{ lib, ... }: with lib;
{
  # interface
  options.deployment.targetEnv = mkOption {
    type = with types; nullOr str;
    default = null;
    description = ''
      This option specifies the type of the environment in which the
      machine is to be deployed by `teraflops`.
    '';
  };

  options.deployment.provisionSSHKey = mkOption {
    type = types.bool;
    default = true;
    description = ''
      This option specifies whether to let `teraflops` provision SSH deployment keys.

      `teraflops` will by default generate an SSH key, store the private key in its state file,
      and add the public key to the remote host.

      Setting this option to `false` will disable this behaviour
      and rely on you to manage your own SSH keys by yourself and to ensure
      that `ssh` has access to any keys it requires.
    '';
  };
}
