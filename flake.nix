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
        python' = pkgs.python312.withPackages(p: [ p.termcolor ]);
      in
      {
        packages.default = pkgs.writers.makeScriptWriter {
          interpreter = python'.interpreter;
          check = "";
        } "/bin/teraflops" ./teraflops/main.py;

        devShells.default = with pkgs;
          mkShell {
            pname = "teraflops";
            packages = [
              python'
            ];
          };
      }
    );
}
