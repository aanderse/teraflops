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
          pname = "teraflops-virtualbox";

          packages = [
            colmena
            jq
            (terraform.withPlugins (p: [ p.tls p.virtualbox ]))
            teraflops.packages.${system}.default
          ];
        };
    } // {
      teraflops = {
        imports = [ teraflops.modules.virtualbox ];

        meta = {
          nixpkgs = nixpkgs.legacyPackages.${system};
        };

        defaults = { config, ... }: {
          deployment.targetEnv = "virtualbox";
          deployment.virtualbox = {
            cpus = 2;
            memory = "1.0 gib";
          };

          system.stateVersion = "23.11";
        };

        machine = { pkgs, ... }: {
          environment.systemPackages = [ pkgs.hello ];
        };
      };
    };
}