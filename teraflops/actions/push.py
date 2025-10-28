
import asyncio
import codecs
import contextlib
import json
import sys

from teraflops import nodes
from teraflops import parsers
from teraflops import ssh
from teraflops import stages
from teraflops.console import Console
from teraflops.utils import generate_terraform_data_for_nix

async def run(args):
  errors = {}
  console = Console(args.verbose)

  async def pipeline(console, name, deployment, terraform_json, drv, private_key):
    try:
      if drv is None:
        drv = await stages.eval(console, name, terraform_json)
      toplevel = await stages.build(console, name, drv)
      await stages.copy(console, name, deployment, toplevel, private_key)
    except Exception as e:
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

    context = contextlib.nullcontext() if args.with_drvs else generate_terraform_data_for_nix()
    async with context as terraform_json:
      if not args.with_drvs:
        console.info('terraform data gathered, ready to do work')

      if args.with_drvs:
        with open(args.with_drvs) as f:
          drvs = json.load(f)

      async with asyncio.TaskGroup() as tg:
        for name, deployment in output_data['nodes'].items():
          if name in selected:
            tg.create_task(pipeline(console, name, deployment, terraform_json, drvs[name] if args.with_drvs else None, private_key))

  for name, e in errors.items():
    if not hasattr(e, 'stderr'):
      console.error('EXCEPTION HAS NO STDERR')
      console.error(e)
      continue

    console.error(f'failed to push to {name} - logs:')

    # https://stackoverflow.com/a/37059682
    value = codecs.escape_decode(e.stderr)[0].decode('utf-8')
    for line in value.splitlines():
      console.error(f'  stderr) {line}')

    console.error(f' failure) child process exited with error code: {e.returncode}')

  if len(errors) != 0:
    sys.exit(1)

def register_action(subparsers):
  parser = subparsers.add_parser('push', parents=[parsers.on(), parsers.with_drvs()], help='copy the closures to remote nodes')
  parser.set_defaults(func=run)
