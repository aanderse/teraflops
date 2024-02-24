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
      outputs = value.outputs or { };
      resources = value.resources or { };
    };

  outputs = terraform.outputs;
  resources =
    let
      eval = address:
        if terraform.resources != { } then
          lib.getAttrFromPath (lib.splitString "." address) terraform.resources
        else
          "\${${address}}"
      ;
    in
      terraform.resources // { inherit eval; exists = terraform.resources != { }; };

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

        config = {
          networking.hostName = mkDefault name;
        };
      };

      output = { nodes, lib, ... }: with lib; {
        teraflops = {
          sensitive = true;
          value = {
            version = 1;
            nodes = mapAttrs (_: node: { inherit (node.config.deployment) tags targetEnv targetHost targetPort targetUser; }) nodes;
          };
        };
      };
    };
  };

  eval = lib.evalModules {
    modules = [
      module
      {
        _module.args.tf.mkAlias = alias: attrs: { __aliases = { "${alias}" = attrs; }; };
      }
      {
        _file = "${flake.outPath}/flake.nix";
        imports = [ flake.outputs.teraflops ];
      }
    ];

    specialArgs = { inherit outputs resources; };
  };
in
  eval
