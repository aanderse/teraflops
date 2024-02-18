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
    provider = flatten (mapAttrsToList (name: attrs: [ { "${name}" = builtins.removeAttrs attrs ["__aliases"]; } ] ++ (mapAttrsToList (k: v: { "${k}" = v; }) (attrs.__aliases or { }))) value.provider);
  }
