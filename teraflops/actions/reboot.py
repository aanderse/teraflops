
import asyncio
import contextlib

from teraflops import nodes
from teraflops import parsers
from teraflops import ssh
from teraflops import stages
from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.utils import generate_terraform_data_for_nix

async def run(args):
  errors = {}
  console = Console(args.verbose)

  async def pipeline(console, name, deployment, terraform_json, private_key):
    try:
      value = await stages.reboot(console, name, deployment, no_wait=args.no_wait, private_key=private_key)

      if not args.no_keys and not args.no_wait:
        await stages.upload_keys(console, name, deployment, terraform_json, private_key)
    except CalledProcessError as e:
      errors[name] = e

  console.info('enumerating nodes...')
  selected, all = await nodes.filter(args)
  if len(all) == len(selected):
    console.info(f'selected all {len(selected)} nodes')
  else:
    console.info(f'selected {len(selected)} out of {len(all)} hosts')

  output_data = await nodes.get_teraflops_data()
  console.info('teraflops data gathered')

  with console.refresh(), ssh.get_private_key(output_data) as private_key:
    context = contextlib.nullcontext() if args.no_keys or args.no_wait else generate_terraform_data_for_nix()
    async with context as terraform_json:
      console.info('terraform data gathered, ready to do work')

      async with asyncio.TaskGroup() as tg:
        for name in selected:
          tg.create_task(pipeline(console, name, output_data['nodes'][name], terraform_json, private_key))

def register_action(subparsers):
  parser = subparsers.add_parser('reboot', parents=[parsers.on(), parsers.no_keys()], help='reboot all nodes in the deployment')
  parser.set_defaults(func=run)
  parser.add_argument('--no-wait', action='store_true', help='do not wait until the nodes are up again - implies --no-keys argument')
