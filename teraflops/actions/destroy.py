
import subprocess

from teraflops import parsers
from teraflops.paths import terraform
from teraflops.utils import generate_full_terraform_config

async def run(args):
  cmd = [terraform(), 'apply', '-destroy']
  if args.confirm:
    cmd += ['-auto-approve']

  async with generate_full_terraform_config():
    subprocess.run(cmd)

def register_action(subparsers):
  parser = subparsers.add_parser('destroy', parents=[parsers.confirm()], help='destroy all resources in the deployment')
  parser.set_defaults(func=run)
