# this file takes a teraflops deploy and turn it into something colmena expects
let
  eval = import ./eval.nix { };
in
  with builtins;
    # pull out all terraform objects so colmena gets what it expects
    removeAttrs eval.config (attrNames eval.options) // {
      # simply pass through meta option to colmena
      inherit (eval.config) meta;
    }
