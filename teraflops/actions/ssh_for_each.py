
import argparse
import asyncio

from teraflops import nodes
from teraflops import parsers
from teraflops import ssh
from teraflops.console import Console

async def run(args):
  console = Console(args.verbose)

  async def doit(console, name, node, command):
    msg = console.message(name)

    if args.verbose:
      console.update(msg, 'executing remote command')

    process = await asyncio.create_subprocess_exec(*ssh.cmd(node, command), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
      console.update(msg, f'failed: {stderr.decode().strip()}', status='failure')
    else:
      console.update(msg, stdout.decode().strip(), status='success')

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
        tg.create_task(doit(console, name, output_data['nodes'][name], args.command))

def register_action(subparsers):
  parser = subparsers.add_parser('ssh-for-each', parents=[parsers.on()], help='execute a command on each machine via SSH')
  parser.set_defaults(func=run)
  parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run')
