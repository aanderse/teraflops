{ pkgs }: with pkgs.lib;
let
  eval = evalModules {
    modules = [
      {
        _file = toString ../teraflops/nix/colmena/options.nix;
        imports = [ (import ../teraflops/nix/colmena/options.nix).deploymentOptions ];
      }
      {
        options._module.args = mkOption {
          # https://github.com/NixOS/nixpkgs/issues/293510
          internal = true;
        };

        config._module = {
          args.pkgs = pkgs;
          args.name = "<name>";

          check = false;
        };
      }
      {
        # provide missing options which are used in teraflops modules
        options.fileSystems = mkOption {
          internal = true;
          type = with types; attrsOf (submodule {
            options = {
              autoFormat = mkOption { internal = true; };
              autoResize = mkOption { internal = true; };
            };
          });
        };
      }

      # nixos module options
      ./deployment.nix
      ../nix/digitalocean/digitalocean.nix
      ../nix/hcloud/hcloud.nix
      ../nix/lxd/lxd.nix
      ../nix/virtualbox/virtualbox.nix
    ];
  };

  doc = pkgs.nixosOptionsDoc {
    inherit (eval) options;

    # https://github.com/NixOS/nixpkgs/blob/25d267ce6e75981df68405af38fbe900ef556c18/nixos/doc/manual/default.nix#L51
    transformOptions = opt: opt // {
      # Clean up declaration sites to not refer to the NixOS source tree.
      declarations =
        map
          (decl:
            if hasPrefix (toString ./..) (toString decl)
            then
              let subpath = removePrefix "/" (removePrefix (toString ./..) (toString decl));
              in { url = "https://github.com/aanderse/teraflops/blob/main/${subpath}"; name = subpath; }
            else decl)
          opt.declarations;
    };
  };
in
  doc.optionsCommonMark
