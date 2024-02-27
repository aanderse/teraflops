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

      virtualbox' = pkgs.terraform-providers.mkProvider {
        hash = "sha256-Oijdx22s7wIDC+Sms097rFVNRF9tzMlUNlPMV7GSsiI=";
        homepage = "https://registry.terraform.io/providers/terra-farm/virtualbox";
        owner = "terra-farm";
        repo = "terraform-provider-virtualbox";
        rev = "v0.2.2-alpha.1";
        spdx = "MIT";
        vendorHash = "sha256-SF11E60OQiRdf+Pf6XyJg60yGRnGOcSzhrYccrWaeYE=";
      };
    in
    {
      devShells.${system}.default = with pkgs;
        mkShell {
          pname = "teraflops-virtualbox";

          packages = [
            colmena
            jq
            (terraform.withPlugins (p: [ virtualbox' ]))
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
            vcpu = 2;
            memorySize = "1.0 gib";
          };

          system.stateVersion = "23.11";
        };

        machine = { pkgs, ... }: {
          environment.systemPackages = [ pkgs.hello ];
        };
      };
    };
}