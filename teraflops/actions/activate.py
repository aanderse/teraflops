
import asyncio
import codecs
import json
import sys

from teraflops import nodes
from teraflops import parsers
from teraflops import ssh
from teraflops import stages
from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.utils import generate_minimal_terraform_config, generate_terraform_data_for_nix

async def run(args):
  errors = {}
  console = Console(args.verbose)

  async def pipeline(console, name, deployment, terraform_json, drv, private_key):
    try:
      if drv is None:
        drv = await stages.eval(console, name, terraform_json)
      toplevel = await stages.build(console, name, drv)
      await stages.copy(console, name, deployment, toplevel, private_key)

      if not args.no_keys and not args.dry_run:
        await stages.upload_keys(console, name, deployment, terraform_json, private_key)

      if args.reboot:
        target = 'boot'
      elif args.dry_run:
        target = 'dry-activate'
      else:
        target = 'switch'

      if target == 'boot' or target == 'switch':
        await stages.switch_profile(console, name, deployment, toplevel, private_key)

      await stages.switch_to_configuration(console, name, deployment, toplevel, target, private_key)

      # TODO: upload post activation keys

      if args.reboot:
        value = await stages.reboot(console, name, deployment, private_key=private_key)

        if not args.no_keys:
          await stages.upload_keys(console, name, deployment, terraform_json, private_key)
      else:
        # TODO: this becomes redundant once we upload post activation keys
        if not args.no_keys and not args.dry_run:
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

    async with generate_terraform_data_for_nix() as terraform_json:
      console.info('terraform data gathered, ready to do work')

      if args.with_drvs:
        with open(args.with_drvs) as f:
          drvs = json.load(f)

      async with asyncio.TaskGroup() as tg:
        for name, deployment in output_data['nodes'].items():
          if name in selected:
            tg.create_task(pipeline(console, name, deployment, terraform_json, drvs[name] if args.with_drvs else None, private_key))

  for name, e in errors.items():
    console.error(f'failed to activate {name} - logs:')

    # https://stackoverflow.com/a/37059682
    value = codecs.escape_decode(e.stderr)[0].decode('utf-8')
    for line in value.splitlines():
      console.error(f'  stderr) {line}')

    console.error(f' failure) child process exited with error code: {e.returncode}')

  if len(errors) != 0:
    sys.exit(1)

def register_action(subparsers):
  parser = subparsers.add_parser('activate', parents=[parsers.on(), parsers.no_keys(), parsers.with_drvs()], help='apply configurations on remote nodes')
  parser.set_defaults(func=run)

  group = parser.add_mutually_exclusive_group()
  group.add_argument('--reboot', action='store_true', help='reboots nodes after activation and waits for them to come back up')
  group.add_argument('--dry-run', action='store_true', help='show what changes would be performed by the activation')
