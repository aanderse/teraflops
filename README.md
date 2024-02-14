# teraflops

> `teraflops` - a terraform ops tool which is sure to be a flop

`teraflops` aims to provide an integrated experience for deployment workflows which involve both [terraform](https://github.com/hashicorp/terraform) and [NixOS](https://github.com/NixOS/nixos) - similar to that of [NixOps](https://github.com/NixOS/nixops). `teraflops` uses the excellent [colmena](https://github.com/zhaofengli/colmena) deployment tool to do most of the heavy lifting, so the following example should look somewhat familiar if you have ever used `colmena`.

```
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }: {
    teraflops =
      # resources - the entire state of terraform as a nix attribute set
      { resources, ... }:
      {
        # meta, exactly as defined in a colmena deploy
        meta = {
          nixpkgs = import nixpkgs {
            system = "x86_64-linux";
          };
        };

        # in this example a single machine is specified
        machine = { modulesPath, name, pkgs, ... }: {
          imports = [ "${modulesPath}/virtualisation/lxc-container.nix" ];

          # we're able to directly pull data from terraform state
          deployment.targetHost = resources.eval "lxd_instance.${name}.ipv4_address";

          environment.systemPackages = [ pkgs.htop ];

          users.users.root.openssh.authorizedKeys.keys = [
            "ssh-ed25519 AAAA..."
          ];
        };

        # exactly as you would define in terraform
        terraform = {
          required_providers = {
            lxd = {
              source = "terraform-lxd/lxd";
              version = ">= 2.0.0";
            };
          };
        };

        resource = { nodes, lib, ... }: with lib; {
          # we're able to create terraform resources based on nixos machines we have defined
          lxd_instance = mapAttrs (name: node: {
            inherit name;
            image = "nixos-23.11";

            file = [
              {
                content = concatStringsSep "\n" node.config.users.users.root.openssh.authorizedKeys.keys;
                target_path = "/root/.ssh/authorized_keys";
              }
            ];
          }) nodes;
        };
      };
  }
}
```

Note the circular nature of the above example: [resource.lxd_instance](https://registry.terraform.io/providers/terraform-lxd/lxd/latest/docs/resources/instance) is defined using `nodes`, an attribute set of our NixOS machines - yet at the same time, `machine` uses `lxd_instance.machine.ipv4_address` to set NixOS options. Additionally, the above example populates the `lxd` container with SSH keys based on configuration from NixOS.

## Usage

The `teraflops` tool has two low level subcommands which get out of your way and let you use the tools you're used to: `terraform` and `colmena`.

```
# anything after 'teraflops tf' is passed directly to terraform
teraflops tf init
teraflops tf apply

# anything after 'teraflops nix' is passed directly to colmena
teraflops nix repl
teraflops nix apply --reboot
```

There is a set of subcommands that act as high level abstraction over the tool that somewhat attempt to mimic parts of the `NixOps` command, but these are experimental and subject to change.

```
teraflops ssh-for-each -- df -h
teraflops scp machine:/root/.ssh/id_ed25519.pub .
```

## Future

I'm experimenting around with some higher level abstractions which directly mimic NixOps plugins. The idea is that one could create various NixOS options under `deployment` to ease creation of NixOS resources. Ideally it would look something like this:

```
{ config, pkgs, lib, ... }: {
  deployment.targetEnv = "hcloud";
  deployment.hcloud = {
    serverType = "cx11";
  };
};
```

This [terranix](https://github.com/terranix/terranix) team has done some really cool work like this.

## Implementation

A very quick `python` script I hacked together which isn't great. Don't look at the code yet... really 😅
