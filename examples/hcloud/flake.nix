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
          pname = "teraflops-hcloud";

          packages = [
            (terraform.withPlugins (p: [
              p.hcloud
              p.ssh
              p.tls
            ]))
            teraflops.packages.${system}.default
          ];
        };
    }
    // {
      teraflops = {
        imports = [ teraflops.modules.hcloud ];

        meta = {
          nixpkgs = nixpkgs.legacyPackages.${system};
        };

        defaults = {
          deployment.targetEnv = "hcloud";
          deployment.hcloud = {
            server_type = "cx11";
            location = "hel1";
          };

          system.stateVersion = "25.05";
        };

        machine =
          { pkgs, ... }:
          {
            # provision a hetzner volume called "storage" and attach to this node
            fileSystems."/storage" = {
              fsType = "ext4";

              hcloud = {
                name = "storage";
                size = 10;
              };
            };

            # provision a hetzner floating ip called "floating-ip" and attach to this node
            networking.interfaces.eth0 = {
              ipv4.addresses = [
                { hcloud.name = "floating-ip"; }
              ];
            };

            environment.systemPackages = [ pkgs.hello ];
          };
      };
    };
}
