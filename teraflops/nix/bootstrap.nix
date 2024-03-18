# this file takes a teraflops deploy and turns it into the minimal amount of terraform code required to run 'terraform show'
let
  flake = builtins.getFlake (toString "%s");
  flakeExpr = flake.outputs.teraflops or { };

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

  # concept taken from https://github.com/NixOS/nixops/blob/master/nix/eval-machine-info.nix

  dummyArgs = f: builtins.listToAttrs (map (a: lib.nameValuePair a false) (builtins.attrNames (builtins.functionArgs f))) // { inherit lib; };

  getImports = expr:
    let
      expr' = if builtins.isPath expr then import expr else expr;
      imports =
        if builtins.isFunction expr' then
          (expr' (dummyArgs expr')).imports or []
        else
          expr'.imports or []
        ;
    in
      [ expr' ] ++ map getImports imports;

  imports = with lib; unique (flatten (getImports flakeExpr));
in
{
  terraform = (lib.evalModules {
    modules = [ { _module.freeformType = jsonType; } ] ++ (map (i: let expr = if builtins.isFunction i then i (dummyArgs i) else i; in expr.terraform or { }) imports);
  }).config;
}
