# this file is used by `hive.nix` and `terraform.nix` to work with a given teraflops deploy specified by `flake`
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

  # arguments that have been set with the 'set-args' command
  arguments = with builtins; fromJSON (readFile ./arguments.json);

  terraform =
    let
      # `terraform.json` is a slightly processed version of `terraform show -json` produced by `teraflops` for consumption here
      value = with builtins; lib.optionalAttrs (pathExists ./terraform.json) (fromJSON (readFile ./terraform.json));
    in
    {
      outputs = value.outputs or null;
      resources = value.resources or null;
    };

  module = { options, config, lib, ... }: with lib; {
    options = {
      # pass directly to colmena
      meta = mkOption {
        type = with types; attrsOf unspecified;
        default = { };
      };
    } // genAttrs [ "check" "data" "locals" "module" "output" "provider" "removed" "resource" "run" "terraform" "variable" ] (value: mkOption {
      # provide an option for every (useful?) type of top level terraform object
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

        config = {
          networking.hostName = mkDefault name;
        };
      };

      terraform = {
        # TODO: keep this in sync with bootstrap.nix
        required_providers = {
          tls = {
            version = ">= 4.0.4";
          };
        };
      };

      resource = { nodes, lib, ... }: with lib;
        let
          nodes' = filterAttrs (_: node: node.config.deployment.provisionSSHKey) nodes;
        in
        {
          # inject a ssh private key terraform resource if `provisionSSHKey` is set
          tls_private_key = mkIf (nodes' != {}) {
            teraflops = {
              algorithm = "ED25519";
            };
          };

          # store teraflops arguments (see set-args and show-args commands) in a terraform_data resource
          terraform_data = mkIf (arguments != { }) {
            teraflops-arguments.input = arguments;
          };
        };

      # `colmena exec` is relatively slow because it needs to do a nix evaluation every time it is run
      # since `teraflops` has state this can be used to speed up the equivalent operation, `teraflops ssh-for-each`
      #
      # inject a terraform output which can be used by the `teraflops` tool for quick access to important data
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
          toSet = value: "\${toset(${lib.generators.toJSON { } value})}";
        };
      }
      {
        _file = "${flake.outPath}/flake.nix";
        imports = [ flake.outputs.teraflops ];
      }
    ];

    # provide terraform resources as specialArgs so they can be used to alter the structure of a teraflops `config`
    specialArgs = { inherit (terraform) outputs resources; } // arguments;
  };
in
  eval
