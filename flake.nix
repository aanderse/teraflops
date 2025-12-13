{
  description = "teraflops - a terraform ops tool which is sure to be a flop";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs?ref=nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-darwin"
        "x86_64-linux"
      ];
    in
    {
      devShells = nixpkgs.lib.genAttrs systems (system: {
        default = nixpkgs.legacyPackages.${system}.mkShell {
          pname = "teraflops";

          inputsFrom = [ self.packages.${system}.default ];

          packages = with nixpkgs.legacyPackages.${system}; [
            nixfmt
            ruff
            statix
          ];
        };
      });

      packages = nixpkgs.lib.genAttrs systems (
        system:
        let
          package = nixpkgs.legacyPackages.${system}.python313.pkgs.callPackage ./nix/teraflops.nix { };
        in
        {
          default = package;
          teraflops = package;
        }
      );

      modules = {
        digitalocean = import ./nix/digitalocean;
        hcloud = import ./nix/hcloud;
        incus = import ./nix/incus;
        linode = import ./nix/linode;
        lxd = import ./nix/lxd;
        virtualbox = import ./nix/virtualbox;
      };
    };
}
