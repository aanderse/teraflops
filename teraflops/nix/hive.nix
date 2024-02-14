let
  eval = import ./eval.nix { };
in
  with builtins; removeAttrs eval.config (attrNames eval.options) // { inherit (eval.config) meta; }
