{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    teraflops.url = "github:aanderse/teraflops";
    teraflops.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { nixpkgs, teraflops, ... }:
    let
      system = "x86_64-linux";

      pkgs = nixpkgs.legacyPackages.${system};

      # NOTE: this is a workaround while opentofu support is being improved in nixpkgs... see https://github.com/NixOS/nixpkgs/issues/283015 for details 
      tofuProvider = provider:
        provider.override (oldArgs: {
          provider-source-address =
            pkgs.lib.replaceStrings
              [ "https://registry.terraform.io/providers" ]
              [ "registry.opentofu.org" ]
              oldArgs.homepage;
        });
    in
    {
      devShells.${system}.default = with pkgs;
        mkShell {
          pname = "teraflops-digitalocean";

          packages = [
            colmena
            jq
            (opentofu.withPlugins (p: map tofuProvider [ p.digitalocean p.ssh p.tls ]))
            teraflops.packages.${system}.default
          ];
        };
    } // {
      teraflops = {
        imports = [ teraflops.modules.digitalocean ];

        meta = {
          nixpkgs = nixpkgs.legacyPackages.${system};
        };

        defaults = { ... }: {
          deployment.targetEnv = "digitalocean";
          deployment.digitalocean = {
            region = "fra1";
            size = "s-1vcpu-1gb";
          };

          system.stateVersion = "24.05";
        };

        machine = { pkgs, ... }: {
          fileSystems."/storage" = {
            fsType = "ext4";
            label = "storage";
            digitalocean.size = 10;
          };

          environment.systemPackages = [ pkgs.hello ];
        };
      };
    };
}
