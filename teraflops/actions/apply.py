
import subprocess

from teraflops import parsers
from teraflops.utils import generate_full_terraform_config



TERRAFORM_EXE = 'terraform'




async def run(args):
  cmd = [TERRAFORM_EXE, 'apply']
  if args.confirm:
    cmd += ['-auto-approve']

  async with generate_full_terraform_config():
    subprocess.run(cmd)

def register_action(subparsers):
  parser = subparsers.add_parser('apply', parents=[parsers.confirm()], help='create or update all resources in the deployment')
  parser.set_defaults(func=run)
