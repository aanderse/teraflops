# teraflops

> `teraflops` - a terraform ops tool which is sure to be a flop

`teraflops` aims to provide an integrated experience for deployment workflows which involve both [terraform](https://github.com/hashicorp/terraform) and [NixOS](https://github.com/NixOS/nixos) - similar to that of [NixOps](https://github.com/NixOS/nixops). `teraflops` uses the excellent [colmena](https://github.com/zhaofengli/colmena) deployment tool to do most of the heavy lifting, so the following example should look somewhat familiar if you have ever used `colmena`.

```
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    teraflops.url = "github:aanderse/teraflops";
  };

  outputs = { nixpkgs, teraflops, ... }: {
    teraflops = {
      imports = [ teraflops.modules.hcloud ];

      meta = {
        nixpkgs = import nixpkgs {
          system = "x86_64-linux";
        };
      };

      machine = { pkgs, ... }: {
        deployment.targetEnv = "hcloud";
        deployment.hcloud = {
          server_type = "cx11";
          location = "nbg1";
        };

        environment.systemPackages = [ pkgs.htop ];
      };

      # if desired you can write terraform code directly inside your teraflops modules
      terraform = {
        backend.s3 = {
          bucket = "mybucket";
          key = "path/to/my/key";
          region = "us-east-1";
        };
      };
    };
  }
}
```

## Usage

The `teraflops` tool has a number of high level commands that often resemble the `NixOps` CLI.

```
# prepare your terraform state in the current working directory
teraflops init

# applies all terraform state and deploys your NixOS configuration
teraflops deploy --reboot --confirm

# perform some operational commands
teraflops ssh-for-each -- df -h
teraflops scp machine:/root/.ssh/id_ed25519.pub .

# NixOS introspection
teraflops repl
teraflops eval '{ nodes, ... }: builtins.attrNames nodes'
```

Additionally there are two low level subcommands which get out of your way and let you use the tools you're used to: `terraform` and `colmena`.

```
# 'teraflops tf' is a direct passthrough to terraform
teraflops tf init
teraflops tf apply

# 'teraflops nix' is a direct passthrough to colmena
teraflops nix repl
teraflops nix apply --reboot
```

## Implementation

A very quick `python` script I hacked together which isn't great. Don't look at the code yet... really 😅

## See also

- [colmena](https://github.com/zhaofengli/colmena) - used by `teraflops` to manage deployments
- [NixOps](https://github.com/NixOS/nixops) - inspiration for `teraflops`
- [terranix](https://github.com/terranix/terranix) - inspiration for `teraflops`
