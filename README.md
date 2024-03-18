# teraflops

> `teraflops` - a terraform ops tool which is sure to be a flop

`teraflops` aims to provide an integrated experience for deployment workflows which involve both [terraform](https://github.com/hashicorp/terraform) and [NixOS](https://github.com/NixOS/nixos) - similar to that of [NixOps](https://github.com/NixOS/nixops). `teraflops` uses the excellent [colmena](https://github.com/zhaofengli/colmena) deployment tool to do most of the heavy lifting, so the following example should look somewhat familiar if you have ever used `colmena`.

```nix
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

```sh
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

```sh
# 'teraflops tf' is a direct passthrough to terraform
teraflops tf init
teraflops tf apply

# 'teraflops nix' is a direct passthrough to colmena
teraflops nix repl
teraflops nix apply --reboot
```

## Deployment arguments

`terapflops` implements the `set-args` command from [NixOps](https://github.com/NixOS/nixops/blob/master/doc/overview.rst#network-arguments). Referencing the example from `NixOps`:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    teraflops.url = "github:aanderse/teraflops";
  };

  outputs = { nixpkgs, teraflops, ... }: {
    teraflops =
      { maintenance ? false }:
      {
        machine =
          { config, pkgs, ... }:
          { services.httpd.enable = maintenance;
            ...
          };
      };
  };
}
```

You can pass deployment arguments using the `set-args` command. For example, if we want to set the `maintenance` argument to `true` in the previous example, you can run:

```sh
teraflops set-args --arg maintenance true
```

## Special arguments

In addition to the regular `nix` module inputs and those defined by calls to the `set-args` command the following arguments are available to `teraflops` modules:

- `outputs`: The fully evaluated [terraform output values](https://developer.hashicorp.com/terraform/language/values/outputs). Generally these aren't as useful in `teraflops` as they are in `terraform` because the `teraflops eval` command has full access to a `resources` argument which accounts for _most_ use cases in `terraform`.
- `resources`: The fully evaluated `terraform` resource set, which includes `resource`, `data`, `module`, etc... objects representing the full state of your deployment.
- `tf`: A minor helper which is most useful for the `tf.ref` function it contains which is used to create `terraform` references, just like in [terranix](https://terranix.org/news/2023-05-24_release-2.6.0.html).

_NOTE:_ Both `outputs` and `resources` will be `null` when a `teraflops` module is evaluated for the purpose of generating `terraform` code in order to avoid recursion.

## Comparison

### colmena

- `colmena` is entirely stateless
- `teraflops` can make full use of `terraform` state

### terranix

- `terranix` builds a high level `nix` api on top of `terraform` which includes full build time validation
- `teraflops` exposes `terraform` directly to you through `nix`, sacraficing build time validation in favor of run time validation in order to make the development of various `teraflops` backends (like `digitalocean`, `hetznercloud`, `linode`, `lxd`, etc...) extremely quick and easy in the spirit of [RFC42](https://github.com/NixOS/rfcs/blob/master/rfcs/0042-config-option.md#part-2-balancing-module-option-count)

- `terranix` focuses on `terraform` code generation and leaves NixOS integration to the user
- `teraflops` provides full and direct integration with NixOS

### NixOps

- `NixOps` builds a high level `nix` api on top of various cloud providers which includes full build time validation, though requires extensive `python` development for every backend desired, many of which do not yet exist
- `teraflops` leverags `terraform` for all of this work so as long as a `terraform` backend exists it is near trivial to create a `teraflops` module for it

- `NixOps` development is has lagged for a number of years, though apparently there are [plans](https://github.com/NixOS/nixops/issues/1574#issuecomment-1866651601) to bring it back!
- `teraflops` is a young project and relies on established software like `colmena`, `terraform`, and `nixos-infect` to provide all major functionality making `teraflops` already quite a capable tool

## Implementation

A very quick `python` script I hacked together which isn't great. Don't look at the code yet... really 😅

## See also

- [colmena](https://github.com/zhaofengli/colmena) - used by `teraflops` to manage deployments
- [NixOps](https://github.com/NixOS/nixops) - inspiration for `teraflops`
- [nixos-infect](https://github.com/elitak/nixos-infect) - used by `teraflops` for integration with various cloud providers
- [terranix](https://github.com/terranix/terranix) - inspiration for `teraflops`
