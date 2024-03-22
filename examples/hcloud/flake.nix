{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    teraflops.url = "github:aanderse/teraflops";
    teraflops.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { nixpkgs, teraflops, ... }:
    let
      system = "x86_64-linux";

      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
    in
    {
      devShells.${system}.default = with pkgs;
        mkShell {
          pname = "teraflops-hcloud";

          packages = [
            colmena
            jq
            (terraform.withPlugins (p: [ p.hcloud p.ssh p.tls ]))
            teraflops.packages.${system}.default
          ];
        };
    } // {
      teraflops = {
        imports = [ teraflops.modules.hcloud ];

        meta = {
          nixpkgs = nixpkgs.legacyPackages.${system};
        };

        defaults = { ... }: {
          deployment.targetEnv = "hcloud";
          deployment.hcloud = {
            server_type = "cx11";
            location = "hel1";
          };

          system.stateVersion = "23.11";
        };

        machine = { pkgs, ... }: {
          environment.systemPackages = [ pkgs.hello ];
        };
      };
    };
}
