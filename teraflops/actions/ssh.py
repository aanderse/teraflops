
import subprocess

from teraflops import nodes
from teraflops import ssh

async def run(args):
  output_data = await nodes.get_teraflops_data()

  node = output_data['nodes'][args.node]

  subprocess.run(ssh.cmd(node))

def register_action(subparsers):
  parser = subparsers.add_parser('ssh', help='login on the specified machine via SSH')
  parser.set_defaults(func=run)
  parser.add_argument('node', type=str, help='identifier of the node')
