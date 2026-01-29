# teraflops

> `teraflops` - a terraform ops tool which is sure to be a flop

`teraflops` version `2` aims to provide an integrated experience for deployment workflows which involve both [terraform](https://github.com/hashicorp/terraform) and [NixOS](https://github.com/NixOS/nixos) - similar to that of [NixOps](https://github.com/NixOS/nixops). `teraflops` has some similarities to the excellent [colmena](https://github.com/zhaofengli/colmena) deployment tool, so the following example should look somewhat familiar if you have ever used `colmena`.

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

## Special arguments

In addition to the regular `nix` module inputs the following arguments are available to `teraflops` modules:

- `outputs`: The fully evaluated [terraform output values](https://developer.hashicorp.com/terraform/language/values/outputs). Generally these aren't as useful in `teraflops` as they are in `terraform` because the `teraflops eval` command has full access to a `resources` argument which accounts for _most_ use cases in `terraform`.
- `resources`: The fully evaluated `terraform` resource set, which includes `resource`, `data`, `module`, etc... objects representing the full state of your deployment.
- `tf`: A minor helper which is most useful for the `tf.ref` function it contains which is used to create `terraform` references, just like in [terranix](https://terranix.org/news/2023-05-24_release-2.6.0.html).

_NOTE:_ Both `outputs` and `resources` will be `null` when a `teraflops` module is evaluated for the purpose of generating `terraform` code in order to avoid recursion.

## `opentofu` support

`teraflops` provides support for `opentofu` via `nixpkgs`. See [examples/opentofu](examples/opentofu/flake.nix) for a working example.

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
- `teraflops` leverages `terraform` for all of this work so as long as a `terraform` backend exists it is near trivial to create a `teraflops` module for it

- `NixOps` development is has lagged for a number of years, though apparently there are [plans](https://github.com/NixOS/nixops/issues/1574#issuecomment-1866651601) to bring it back!
- `teraflops` is a young project and relies on established software like `terraform` and `nixos-infect` to provide all major functionality making `teraflops` already quite a capable tool

## Implementation

A `python` program making heavy use of `async` to make operation of your deploys as fast as possible. Code quality is a work in progress... PRs welcome and accepted 😅

## See also

- [colmena](https://github.com/zhaofengli/colmena) - inspiration for `teraflops`, was used in version 1 of `teraflops`
- [NixOps](https://github.com/NixOS/nixops) - inspiration for `teraflops`
- [nixos-infect](https://github.com/elitak/nixos-infect) - used by `teraflops` for integration with various cloud providers
- [terranix](https://github.com/terranix/terranix) - inspiration for `teraflops`
