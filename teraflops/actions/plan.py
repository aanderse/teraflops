import subprocess

from teraflops.paths import terraform
from teraflops.utils import generate_full_terraform_config


async def run(args):
    async with generate_full_terraform_config():
        subprocess.run([terraform(), 'plan'])


def register_action(subparsers):
    parser = subparsers.add_parser('plan', help='show changes required by the current configuration')
    parser.set_defaults(func=run)
