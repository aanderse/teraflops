
import subprocess

from teraflops import parsers
from teraflops.paths import terraform
from teraflops.utils import generate_full_terraform_config

async def run(args):
  cmd = [terraform(), 'apply']
  if args.confirm:
    cmd += ['-auto-approve']

  async with generate_full_terraform_config():
    subprocess.run(cmd)

def register_action(subparsers):
  parser = subparsers.add_parser('apply', parents=[parsers.confirm()], help='create or update all resources in the deployment')
  parser.set_defaults(func=run)
