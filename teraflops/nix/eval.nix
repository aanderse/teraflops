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

  resources =
    let
      value = with builtins; lib.optionalAttrs (pathExists ./resources.json) (fromJSON (readFile ./resources.json));
      eval = address:
        if builtins.pathExists ./resources.json then
          lib.getAttrFromPath (lib.splitString "." address) value
        else
          "\${${address}}"
      ;
    in
      value // { inherit eval; };

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
            nodes = mapAttrs (_: node: { inherit (node.config.deployment) tags targetHost targetPort targetUser; }) nodes;
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

    specialArgs = { inherit resources; };
  };
in
  eval
