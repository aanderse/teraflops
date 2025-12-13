{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    teraflops.url = "github:aanderse/teraflops";
    teraflops.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    { nixpkgs, teraflops, ... }:
    let
      system = "x86_64-linux";

      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
    in
    {
      devShells.${system}.default =
        with pkgs;
        mkShell {
          pname = "teraflops-digitalocean";

          packages = [
            (terraform.withPlugins (p: [
              p.digitalocean
              p.ssh
              p.tls
            ]))
            teraflops.packages.${system}.default
          ];
        };
    }
    // {
      teraflops = {
        imports = [ teraflops.modules.digitalocean ];

        meta = {
          nixpkgs = nixpkgs.legacyPackages.${system};
        };

        defaults = {
          deployment.targetEnv = "digitalocean";
          deployment.digitalocean = {
            region = "fra1";
            size = "s-1vcpu-1gb";
          };

          system.stateVersion = "25.05";
        };

        machine =
          { pkgs, ... }:
          {
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
