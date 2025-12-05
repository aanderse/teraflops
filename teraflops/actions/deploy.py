
import asyncio
import codecs
import subprocess
import sys

from teraflops import nodes
from teraflops import parsers
from teraflops import ssh
from teraflops import stages
from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.paths import terraform
from teraflops.utils import generate_full_terraform_config, generate_terraform_data_for_nix

async def wait_for_node(console, name, node, private_key):
  msg = None

  while True:
    # see https://github.com/zhaofengli/colmena/issues/166#issuecomment-1892325999
    proc = await asyncio.create_subprocess_exec(*ssh.cmd(node, ['cat', '/proc/sys/kernel/random/boot_id'], private_key, ['-o', 'ConnectTimeout=10']), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)

    if await proc.wait() == 0:
      break

    if not msg:
      msg = console.message(name, 'waiting for node to become available')

    await asyncio.sleep(2)

  if msg:
    console.update(msg, description='node is now available', status='success')

async def run(args):
  errors = {}
  console = Console(args.verbose)

  async def pipeline(console, name, deployment, terraform_json, private_key):
    try:
      await wait_for_node(console, name, node, private_key)

      drv = await stages.eval(console, name, terraform_json)
      toplevel = await stages.build(console, name, drv)
      await stages.copy(console, name, deployment, toplevel, private_key)

      if not args.no_keys:
        await stages.upload_keys(console, name, deployment, terraform_json, private_key)

      await stages.switch_profile(console, name, deployment, toplevel, private_key)
      await stages.switch_to_configuration(console, name, deployment, toplevel, 'boot' if args.reboot else 'switch', private_key)

      # TODO: upload post activation keys

      if args.reboot:
        value = await stages.reboot(console, name, deployment, private_key)

        if not args.no_keys:
          await stages.upload_keys(console, name, deployment, terraform_json, private_key)
      else:
        # TODO: this becomes redundant once we upload post activation keys
        if not args.no_keys:
          await stages.upload_keys(console, name, deployment, terraform_json, private_key)

    except CalledProcessError as e:
      errors[name] = e

  # apply terraform configuration
  cmd = [terraform(), 'apply']
  if args.confirm:
    cmd += ['-auto-approve']

  async with generate_full_terraform_config():
    subprocess.run(cmd)
  # apply terraform configuration

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
      async with asyncio.TaskGroup() as tg:
        for name, node in output_data['nodes'].items():
          if name in selected:
            tg.create_task(pipeline(console, name, node, terraform_json, private_key))

  for name, e in errors.items():
    console.error(f'failed to deploy {name} - logs:')

    # https://stackoverflow.com/a/37059682
    value = codecs.escape_decode(e.stderr)[0].decode('utf-8')
    for line in value.splitlines():
      console.error(f'  stderr) {line}')

    console.error(f' failure) child process exited with error code: {e.returncode}')

  if len(errors) != 0:
    sys.exit(1)

def register_action(subparsers):
  parser = subparsers.add_parser('deploy', parents=[parsers.confirm(), parsers.on(), parsers.no_keys()], help='deploy the configuration')
  parser.set_defaults(func=run)
  parser.add_argument('--reboot', action='store_true', help='reboots nodes after activation and waits for them to come back up')
