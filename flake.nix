{
  description = "teraflops - a terraform ops tool which is sure to be a flop";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        packages.default = pkgs.python312.pkgs.callPackage ./nix/teraflops.nix {};

        devShells.default = with pkgs;
          mkShell {
            pname = "teraflops";

            inputsFrom = [ self.packages.${system}.default ];
          };
      }
    ) // {
      modules = {
        hcloud = import ./nix/hcloud;
        virtualbox = import ./nix/virtualbox;
      };
    };
}
