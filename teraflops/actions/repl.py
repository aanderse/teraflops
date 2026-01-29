import subprocess
from importlib.resources import files

from teraflops.paths import flake_ref, nix
from teraflops.utils import generate_terraform_data_for_nix

eval_path = files('teraflops.nix').joinpath('eval.nix')


async def run(args):
    async with generate_terraform_data_for_nix() as terraform_json:
        cmd = [
            nix(),
            'repl',
            '--extra-experimental-features',
            'flakes nix-command',
            '--expr',
            f"""
              with import {eval_path} {{
                flake = {flake_ref()};
                terraform_json = {terraform_json};
              }}; repl
            """,
        ]
        if args.debugger:
            cmd += ['--debugger']

        subprocess.run(cmd, check=True)


def register_action(subparsers):
    parser = subparsers.add_parser('repl', help='start an interactive REPL with the complete configuration')
    parser.set_defaults(func=run)
    parser.add_argument('--debugger', action='store_true', help='start an interactive environment if evaluation fails')
