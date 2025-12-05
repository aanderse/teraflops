
import subprocess

from teraflops.paths import terraform
from teraflops.utils import generate_minimal_terraform_config

async def run(args):
  cmd = [terraform(), 'init']
  if args.migrate_state:
    cmd += ['-migrate-state']
  if args.reconfigure:
    cmd += ['-reconfigure']
  if args.upgrade:
    cmd += ['-upgrade']

  async with generate_minimal_terraform_config(use_cache_if_available=False):
    subprocess.run(cmd, check=True)

def register_action(subparsers):
    parser = subparsers.add_parser('init', help='prepare your working directory for other commands')
    parser.set_defaults(func=run)
    parser.add_argument('--migrate-state', action='store_true', help='reconfigure a backend, and attempt to migrate any existing state')
    parser.add_argument('--reconfigure', action='store_true', help='reconfigure a backend, ignoring any saved configuration')
    parser.add_argument('--upgrade', action='store_true', help='install the latest module and provider versions allowed within configured constraints, overriding the default behavior of selecting exactly the version recorded in the dependency lockfile.')
