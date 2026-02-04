{ name, lib, ... }:
let
  keyType =
    {
      lib,
      name,
      config,
      ...
    }:
    {
      options = {
        name = lib.mkOption {
          type = lib.types.str;
          default = name;
          description = ''
            File name of the key.
          '';
        };

        text = lib.mkOption {
          type = lib.types.str;
          description = ''
            Content of the key.
          '';
        };

        destDir = lib.mkOption {
          type = lib.types.path;
          default = "/run/keys";
          description = ''
            Destination directory on the host.
          '';
        };

        path = lib.mkOption {
          type = lib.types.path;
          default = "${config.destDir}/${config.name}";
          internal = true;
          description = ''
            Full path to the destination.
          '';
        };

        user = lib.mkOption {
          type = lib.types.str;
          default = "root";
          description = ''
            The group that will own the file.
          '';
        };

        group = lib.mkOption {
          type = lib.types.str;
          default = "root";
          description = ''
            The group that will own the file.
          '';
        };

        permissions = lib.mkOption {
          type = lib.types.str;
          default = "0600";
          description = ''
            Permissions to set for the file.
          '';
        };
      };
    };
in
{
  options = {
    deployment = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = ''
          Whether to include this node in the deployment.

          Set to `false` to exclude a node that is defined in an imported
          module without removing its definition.
        '';
      };

      targetHost = lib.mkOption {
        type = with lib.types; nullOr str;
        default = name;
        description = ''
          The target SSH node for deployment.

          By default, the node's attribute name will be used.
          If set to null, only local deployment will be supported.
        '';
      };

      targetPort = lib.mkOption {
        type = with lib.types; nullOr types.port;
        default = null;
        description = ''
          The target SSH port for deployment.

          By default, the port is the standard port (22) or taken
          from your ssh_config.
        '';
      };

      targetUser = lib.mkOption {
        default = "root";
        type = with lib.types; nullOr str;
        description = ''
          The user to use to log into the remote node. If set to null, the
          target user will not be specified in SSH invocations.
        '';
      };

      tags = lib.mkOption {
        type = with lib.types; listOf str;
        default = [ ];
        description = ''
          A list of tags for the node.

          Can be used to select a group of nodes for deployment.
        '';
      };

      sshOptions = lib.mkOption {
        type = with lib.types; listOf str;
        default = [ ];
        description = ''
          Extra options to pass to SSH when connecting to this node.
        '';
        example = [ "-o" "ProxyJump=bastion" ];
      };

      keys = lib.mkOption {
        type = lib.types.attrsOf (lib.types.submodule keyType);
        default = { };
        description = ''
          A set of secrets to be deployed to the node.

          Secrets are transferred to the node out-of-band and
          never ends up in the Nix store.
        '';
      };
    };
  };
}
