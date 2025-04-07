
import asyncio

from teraflops import nodes
from teraflops import ssh
from teraflops.console import Console

async def run(args):
  console = Console(args.verbose)
  async def doit(console, name, node, command):
    # TODO: too verbose?
    msg = console.message(name, f'executing {command} on {node["targetHost"]}')

    process = await asyncio.create_subprocess_exec(*ssh.cmd(node, ['uptime']), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await process.communicate()

    if process.returncode != 0:
      console.update(msg, 'unavailable', status='failure')
    else:
      console.update(msg, stdout.decode().strip(), status='success')

  output_data = await nodes.get_teraflops_data()

  with console.refresh():
    async with asyncio.TaskGroup() as tg:
      for name, deployment in output_data['nodes'].items():
        tg.create_task(doit(console, name, deployment, ['uptime']))

def register_action(subparsers):
  parser = subparsers.add_parser('check', help='attempt to connect to each node via SSH and print the results of the uptime command.')
  parser.set_defaults(func=run)
