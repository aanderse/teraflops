{
  flake ? builtins.getFlake "git+file://${toString ../..}",
  terraform_json ? null,
}:
let
  inherit (flake.inputs.nixpkgs) lib;

  # copy/paste from nixpkgs/pkgs/pkgs-lib/formats.nix
  jsonType =
    with lib.types;
    let
      valueType =
        nullOr (oneOf [
          bool
          int
          float
          str
          path
          (attrsOf valueType)
          (listOf valueType)
        ])
        // {
          description = "JSON value";
        };
    in
    valueType;

  terraform =
    let
      # `terraform.json` is a slightly processed version of `terraform show -json` produced by `teraflops` for consumption here
      value = lib.optionalAttrs (terraform_json != null) (
        builtins.fromJSON (builtins.readFile terraform_json)
      );
    in
    {
      outputs = value.outputs or null;
      resources = value.resources or null;
    };

  uuid = terraform.resources.random_uuid.teraflops.id or "\${random_uuid.teraflops.id}";

  module =
    { lib, ... }:
    {
      options = {
        meta = lib.mkOption {
          type = with lib.types; attrsOf unspecified;
          default = { };
        };

        defaults = lib.mkOption {
          type = lib.types.deferredModule;
          default = { };
        };

        nodes = lib.mkOption {
          type = with lib.types; attrsOf deferredModule;
          default = { };
          description = ''
            Attribute set of NixOS machine configurations to be deployed by teraflops.
          '';
        };

        testScript = lib.mkOption {
          type = with lib.types; nullOr (either str (functionTo str));
          default = null;
          description = ''
            Python test script to run against deployed machines.

            Machines are injected as globals by name.
            Can be a string or a function that receives
            `{ nodes, pkgs, lib, resources, outputs }` and returns a string.
          '';
        };
      }
      // lib.genAttrs [ "module" "terraform" ] (
        value:
        lib.mkOption {
          type = jsonType;
          default = { };
        }
      )
      //
        lib.genAttrs
          [
            "check"
            "data"
            "ephemeral"
            "locals"
            "output"
            "provider"
            "removed"
            "resource"
            "run"
            "variable"
          ]
          (
            value:
            lib.mkOption {
              type = lib.types.submoduleWith {
                shorthandOnlyDefinesConfig = true;
                modules = lib.singleton {
                  _module.freeformType = jsonType;
                };
                specialArgs = {
                  inherit nodes;
                };
              };
              default = { };
            }
          );

      config = {
        # allow top-level node definitions for backwards compatibility
        _module.freeformType = with lib.types; attrsOf deferredModule;

        terraform = {
          required_providers = {
            random = {
              source = "hashicorp/random";
              version = ">= 3.0";
            };
            tls = {
              version = ">= 4.0.4";
            };
          };
        };

        resource =
          { nodes, lib, ... }:
          let
            nodes' = lib.filterAttrs (_: node: node.config.deployment.provisionSSHKey) nodes;
          in
          lib.mkMerge [
            {
              random_uuid.teraflops = { };
            }
            (lib.mkIf (nodes' != { }) {
              # inject a ssh private key terraform resource if `provisionSSHKey` is set
              tls_private_key = {
                teraflops = {
                  algorithm = "ED25519";
                };
              };
            })
          ];

        # `colmena exec` is relatively slow because it needs to do a nix evaluation every time it is run
        # since `teraflops` has state this can be used to speed up the equivalent operation, `teraflops ssh-for-each`
        #
        # inject a terraform output which can be used by the `teraflops` tool for quick access to important data
        output =
          { nodes, lib, ... }:
          let
            nodes' = lib.filterAttrs (_: node: node.config.deployment.provisionSSHKey) nodes;
          in
          {
            teraflops = {
              sensitive = true;
              value = {
                version = 2;
                nodes = lib.mapAttrs (_: node: {
                  inherit (node.config.deployment)
                    provisionSSHKey
                    sshOptions
                    tags
                    targetEnv
                    targetHost
                    targetPort
                    targetUser
                    ;
                }) nodes;
                privateKey = if nodes' != { } then "\${tls_private_key.teraflops.private_key_openssh}" else null;
                uuid = "\${random_uuid.teraflops.id}";
              };
            };
          };

        defaults =
          {
            name,
            config,
            lib,
            ...
          }:
          {
            options.deployment.targetEnv = lib.mkOption {
              type = with lib.types; nullOr str;
              default = null;
              description = ''
                This option specifies the type of the environment in which the
                machine is to be deployed by `teraflops`.
              '';
            };

            options.deployment.provisionSSHKey = lib.mkOption {
              type = lib.types.bool;
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
              networking.hostName = lib.mkDefault name;

              users.users.${config.deployment.targetUser}.openssh.authorizedKeys.keys = lib.optionals (
                config.deployment.provisionSSHKey && terraform.resources ? tls_private_key
              ) [ terraform.resources.tls_private_key.teraflops.public_key_openssh ];
            };
          };
      };
    };

  eval = lib.evalModules {
    modules = [
      module
      {
        _module.args.uuid = uuid;
        _module.args.tf = {
          mkAlias = alias: attrs: {
            __aliases = {
              "${alias}" = attrs;
            };
          };
          ref = ref: "\${${ref}}";
          toMap = value: "\${tomap(${lib.generators.toJSON { } value})}";
          toSet = value: "\${toset(${lib.generators.toJSON { } value})}";
        };
      }
      {
        _file = flake.outPath + "/flake.nix";
        imports = [ flake.outputs.teraflops ];
      }
    ];

    specialArgs = { inherit (terraform) outputs resources; };
  };

  ##########################

  pkgs = eval.config.meta.nixpkgs;
  evalConfig = import (pkgs.path + "/nixos/lib/eval-config.nix");

  # support both top-level node definitions (legacy) and explicit `nodes` option
  topLevelNodes = builtins.removeAttrs eval.config (builtins.attrNames eval.options);

  # merge all node names from both sources
  allNodeNames = lib.unique (
    builtins.attrNames eval.config.nodes ++ builtins.attrNames topLevelNodes
  );

  allNodes = lib.genAttrs allNodeNames (
    name:
    let
      # collect modules from both sources
      nodeModules =
        lib.optionals (eval.config.nodes ? ${name}) [ eval.config.nodes.${name} ]
        ++ lib.optionals (topLevelNodes ? ${name}) [ topLevelNodes.${name} ];
    in
    evalConfig {
      modules = [
        eval.config.defaults

        # slimmed down option set from colmena... thanks zhaofeng!
        ./deployment.nix

        {
          _module.args = {
            inherit name;
            nodes = allNodes;
          };

          nixpkgs.pkgs = pkgs;
          # nixpkgs.overlays = lib.mkBefore pkgs.overlays;
          # nixpkgs.config = lib.mkBefore pkgs.config;
        }
      ]
      ++ nodeModules;
    }
  );

  # filter out nodes with deployment.enable = false
  nodes = lib.filterAttrs (_: node: node.config.deployment.enable) allNodes;
in
{
  inherit nodes;

  testScript =
    let
      raw = eval.config.testScript;
    in
    if raw == null then
      null
    else if builtins.isFunction raw then
      raw {
        inherit nodes pkgs lib;
        inherit uuid;
        inherit (terraform) resources outputs;
      }
    else
      raw;

  # includes hack to account for provider aliases: https://developer.hashicorp.com/terraform/language/providers/configuration#alias-multiple-provider-configurations
  # equivalent in nix:
  #
  # provider = { lib, ... }: {
  #   aws = lib.mkMerge [
  #     {
  #       region = "us-east-1";
  #     }
  #     (tf.mkAlias "aws" {
  #       alias = "west";
  #       region = "us-west-2";
  #     })
  #   ];
  # };
  terraform = (pkgs.formats.json { }).generate "main.tf.json" (
    lib.filterAttrs (_: v: v != { } && v != [ ]) (
      {
        inherit (eval.config)
          check
          data
          ephemeral
          locals
          module
          output
          provider
          removed
          resource
          run
          terraform
          variable
          ;
      }
      // {
        provider = lib.flatten (
          lib.mapAttrsToList (
            name: attrs:
            [ { "${name}" = builtins.removeAttrs attrs [ "__aliases" ]; } ]
            ++ (lib.mapAttrsToList (k: v: { "${k}" = v; }) (attrs.__aliases or { }))
          ) eval.config.provider
        );
      }
    )
  );

  bootstrap = (pkgs.formats.json { }).generate "main.tf.json" (
    lib.filterAttrs (_: v: v != { }) {
      inherit (eval.config)
        module
        # provider
        terraform
        ;
    }
  );

  evalFn =
    fnOrExpr:
    if builtins.isFunction fnOrExpr then
      fnOrExpr {
        inherit (terraform) resources outputs;
        inherit uuid;
        inherit nodes pkgs lib;
      }
    else
      fnOrExpr;

  repl = {
    inherit (terraform) resources outputs;
    inherit uuid;
    inherit nodes pkgs lib;
  };
}
