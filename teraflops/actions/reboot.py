
import asyncio

from teraflops import nodes
from teraflops import parsers
from teraflops import stages
from teraflops.console import Console

async def run(args):

  console = Console(verbose=True)

  # TODO: some sort of message, right?
  output_data = await nodes.get_teraflops_data()

  console.info('enumerating nodes...')
  selected, all = await nodes.filter(args)
  if len(all) == len(selected):
    console.info(f'selected all {len(selected)} nodes')
  else:
    console.info(f'selected {len(selected)} out of {len(all)} hosts')

  with console.refresh():
    async with asyncio.TaskGroup() as tg:
      for name in selected:
        tg.create_task(stages.reboot(console, name, output_data['nodes'][name], args.no_wait))

def register_action(subparsers):
  parser = subparsers.add_parser('reboot', parents=[parsers.on()], help='reboot all nodes in the deployment')
  parser.set_defaults(func=run)
  parser.add_argument('--no-wait', action='store_true', help='do not wait until the nodes are up again')
