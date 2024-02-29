{ flake ? builtins.getFlake (toString "%s") }:
let
  lib = flake.inputs.nixpkgs.lib;
  jsonType = with lib.types; let
    valueType = nullOr (oneOf [
      bool
      int
      float
      str
      path
      (attrsOf valueType)
      (listOf valueType)
    ]) // {
      description = "JSON value";
    };
  in valueType;

  terraform =
    let
      value = with builtins; lib.optionalAttrs (pathExists ./terraform.json) (fromJSON (readFile ./terraform.json));
    in
    {
      outputs = value.outputs or null;
      resources = value.resources or null;
    };

  module = { options, config, lib, ... }: with lib; {
    options = {
      meta = mkOption {
        type = with types; attrsOf unspecified;
        default = { };
      };
    } // genAttrs [ "check" "data" "locals" "module" "output" "provider" "removed" "resource" "run" "terraform" "variable" ] (value: mkOption {
      type = lib.types.deferredModuleWith {
        staticModules = [
          { _module.freeformType = jsonType; }
        ];
      };
      default = {};
    });

    config = {
      _module.freeformType = with types; attrsOf deferredModule;

      defaults = { name, lib, ... }: with lib; {
        options.deployment.targetEnv = mkOption {
          type = with types; nullOr str;
          default = null;
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

        config = {
          networking.hostName = mkDefault name;
        };
      };

      resource = { nodes, lib, ... }: with lib;
        let
          nodes' = filterAttrs (_: node: node.config.deployment.provisionSSHKey) nodes;
        in
        {
          tls_private_key = mkIf (nodes' != {}) {
            teraflops = {
              algorithm = "ED25519";
            };
          };
        };

      output = { nodes, lib, ... }: with lib;
        let
          nodes' = filterAttrs (_: node: node.config.deployment.provisionSSHKey) nodes;
        in
        {
          teraflops = {
            sensitive = true;
            value = {
              version = 1;
              nodes = mapAttrs (_: node: { inherit (node.config.deployment) provisionSSHKey tags targetEnv targetHost targetPort targetUser; }) nodes;
              privateKey = if nodes' != {} then "\${tls_private_key.teraflops.private_key_openssh}" else null;
            };
          };
        };
    };
  };

  eval = lib.evalModules {
    modules = [
      module
      {
        _module.args.tf = {
          mkAlias = alias: attrs: { __aliases = { "${alias}" = attrs; }; };
          ref = ref: "\${${ref}}";
        };
      }
      {
        _file = "${flake.outPath}/flake.nix";
        imports = [ flake.outputs.teraflops ];
      }
    ];

    specialArgs = { inherit (terraform) outputs resources; };
  };
in
  eval
