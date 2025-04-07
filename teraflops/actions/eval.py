
import asyncio
import contextlib

from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.utils import generate_terraform_data_for_nix



from importlib.resources import files
eval_path = files('teraflops.nix').joinpath('eval.nix')

async def run(args):
  console = Console(args.verbose)

  async def nix_eval_expr(nix_expr, terraform_json):
    cmd_args = [
      '--extra-experimental-features', 'flakes nix-command',
      'eval',
      '--impure',
      '--expr',
      f'(import {eval_path} {{ flake = builtins.getFlake (toString ./.); terraform_json = {terraform_json or "null"}; }}).evalFn ({nix_expr})'
    ]

    if args.json:
      cmd_args += ['--json']
    if args.raw:
      cmd_args += ['--raw']

    process = await asyncio.create_subprocess_exec('nix', *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    return process.returncode, stdout, stderr

  context = contextlib.nullcontext() if args.without_resources else generate_terraform_data_for_nix()
  async with context as terraform_json:
    tasks = [nix_eval_expr(expr, terraform_json) for expr in args.expr]
    for task in asyncio.as_completed(tasks):
      returncode, stdout, stderr = await task

      if returncode != 0:
        raise CalledProcessError(returncode, stdout=stdout, stderr=stderr)

      console.print(stdout.strip().decode())

def register_action(subparsers):
  parser = subparsers.add_parser('eval', help='evaluate an expression using the complete configuration')
  parser.set_defaults(func=run)
  parser.add_argument('expr', type=str, nargs='+', help='the nix expression') # TODO: add an example, { resources, nodes, pkgs, lib, ... }:
  parser.add_argument('--without-resources', action='store_true')

  group = parser.add_mutually_exclusive_group()
  group.add_argument('--json', action='store_true')
  group.add_argument('--raw', action='store_true')
