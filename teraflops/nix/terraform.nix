# this file takes a teraflops deploy and turns it into something terraform expects
{ path ? "%s" }:
let
  colmena = import "${path}/eval.nix" {
    colmenaModules = import "${path}/modules.nix";
    colmenaOptions = import "${path}/options.nix";
    rawHive = import ./hive.nix;
  };
  pkgs = colmena.introspect({ pkgs, ... }: pkgs);
in
  (pkgs.formats.json {}).generate "main.tf.json" (colmena.introspect (
    { nodes, pkgs, lib, ... }: with lib;
    let
      eval = import ./eval.nix { };
      value = filterAttrs (_: v: v != null && v != { })
        (mapAttrs (_: value: let x = (evalModules {
          modules = [ value ];
          specialArgs = { inherit nodes pkgs lib; };
        }).config; in filterAttrs (_: v: v != { }) x) {
          inherit (eval.config)
            check
            data
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
        });
    in
      value // optionalAttrs (value ? provider) {
        # hack to account for provider aliases: https://developer.hashicorp.com/terraform/language/providers/configuration#alias-multiple-provider-configurations
        provider = flatten (mapAttrsToList (name: attrs: [ { "${name}" = builtins.removeAttrs attrs ["__aliases"]; } ] ++ (mapAttrsToList (k: v: { "${k}" = v; }) (attrs.__aliases or { }))) value.provider);
      }
  ))
