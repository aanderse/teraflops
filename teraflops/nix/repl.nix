{ path ? "%s" }:
let
  colmena = import "${path}/eval.nix" {
    colmenaModules = import "${path}/modules.nix";
    colmenaOptions = import "${path}/options.nix";
    rawHive = import ./hive.nix;
  };
in
  colmena.introspect ({ nodes, pkgs, lib, ... }:
  let
    arguments = with builtins; fromJSON (readFile ./arguments.json);
    terraform = with builtins; fromJSON (readFile ./terraform.json);
  in
  {
    inherit nodes pkgs lib;
    inherit (terraform) outputs resources;
  } // arguments)
