
import asyncio
import json
import os

from string import Template
from teraflops import ssh
from teraflops.error import CalledProcessError



from importlib.resources import files
eval_path = files('teraflops.nix').joinpath('eval.nix')


async def eval(console, name, terraform_json):
  cmd = [
    'nix-instantiate',
    '--json',
    eval_path,
    '-A',
    f'nodes."{name}".config.system.build.toplevel', '--arg', 'flake', 'builtins.getFlake (toString ./.)', '--argstr', 'terraform_json',
    terraform_json
  ]

  msg = console.message(name, f'evaluating {name}')

  env={}
  process = await asyncio.create_subprocess_exec(*cmd, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

  stderr = b''

  while not process.stderr.at_eof():
    data = await process.stderr.readline()
    stderr += data
    line = data.decode('utf-8').rstrip()

    console.update(msg, line)

  stdout, _ = await process.communicate()

  if process.returncode != 0:
    lines = stderr.decode().rstrip().splitlines()
    if len(lines) > 0:
      console.update(msg, f'evaluation failed: {lines[-1].strip()}', status='failure')
    else:
      console.update(msg, f'evaluation failed: an expected failure occurred', status='failure')

    raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

  toplevel = stdout.decode().strip()
  console.update(msg, f'evaluated {toplevel}', status='success')
  return toplevel

async def build(console, name, drv):
  cmd = [
    'nix-build',
    '--no-out-link',
    drv,
  ]

  msg = console.message(name, f'building {name}')

  env={}
  process = await asyncio.create_subprocess_exec(*cmd, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

  stderr = b''

  while not process.stderr.at_eof():
    data = await process.stderr.readline()
    stderr += data
    line = data.decode('utf-8').rstrip()

    console.update(msg, line)

  stdout, _ = await process.communicate()

  if process.returncode != 0:
    lines = stderr.decode().rstrip().splitlines()
    if len(lines) > 0:
      console.update(msg, f'build failed: {lines[-1].strip()}', status='failure')
    else:
      console.update(msg, f'build failed: an unexpected failure occurred', status='failure')

    raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

  toplevel = stdout.decode().strip()
  console.update(msg, f'built {toplevel}', status='success')

  return toplevel

async def copy(console, name, deployment, toplevel, private_key=None):
  cmd = [
    'nix',
    '--extra-experimental-features', 'flakes nix-command',
    'copy',
    '--to', f'ssh-ng://{deployment["targetUser"]}@{deployment["targetHost"]}?compress=true',
    toplevel,
    '--no-check-sigs',
    '--substitute-on-destination',
    '--verbose'
  ]

  msg = console.message(name, 'pushing system closure')

  env={'NIX_SSHOPTS': ' '.join(ssh.opts(deployment, private_key=private_key))}

  process = await asyncio.create_subprocess_exec(*cmd, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)





  stderr = b''

  while not process.stderr.at_eof():
    data = await process.stderr.readline()
    stderr += data
    line = data.decode('utf-8').rstrip()

    console.update(msg, line)




  await process.wait()

  if process.returncode != 0:
    lines = stderr.decode().rstrip().splitlines()
    # console.info(f'{name} -> len: {len(lines)}, value: "{stderr.decode()}"')
    console.update(msg, f'push failed: {lines[-1].strip()}', status='failure')

    raise CalledProcessError(process.returncode, stderr=stderr)

  console.update(msg, 'pushed system closure', status='success')

async def switch_profile(console, name, node, toplevel, private_key=None):
  msg = console.message(name, 'switching system profile')

  cmd = ssh.cmd(node, [f'nix-env', '-p', '/nix/var/nix/profiles/system', '--set', toplevel], private_key=private_key)

  process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

  stdout = b''

  while not process.stdout.at_eof():
    data = await process.stdout.readline()
    stdout += data
    line = data.decode('utf-8').rstrip()

    console.update(msg, line)

  _, stderr = await process.communicate()

  if process.returncode != 0: # done, error
    console.update(msg, f'switching profile failed: {stderr.decode().strip()}', status='failure')
    raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

  console.update(msg, 'switching profile successful', status='success')

async def switch_to_configuration(console, name, node, toplevel, target, private_key=None):
  msg = console.message(name, 'activating system profile')

  cmd = ssh.cmd(node, [f'{toplevel}/bin/switch-to-configuration', target], private_key=private_key)

  process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

  stdout = b''

  while not process.stdout.at_eof():
    data = await process.stdout.readline()
    stdout += data
    line = data.decode('utf-8').rstrip()

    console.update(msg, line)

  _, stderr = await process.communicate()

  if process.returncode != 0: # done, error
    console.update(msg, f'activation failed: {stderr.decode().strip()}', status='failure')
    raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

  console.update(msg, 'activation successful', status='success')

async def upload_keys(console, name, deployment, terraform_json, private_key=None):
  cmd = [
    'nix',
    '--extra-experimental-features', 'flakes nix-command',
    'eval',
    '--impure',
    '--json',
    '--expr',
    f'(import {eval_path} {{ flake = builtins.getFlake (toString ./.); terraform_json = {terraform_json}; }}).nodes."{name}".config.deployment.keys'
  ]

  msg = console.message(name, 'uploading keys')

  process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
  stdout, stderr = await process.communicate()

  if process.returncode != 0:
    console.update(msg, f'key upload failed: {stderr.decode().strip()}', status='failure')
    raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

  data = json.loads(stdout)

  for key in data.values():
    console.update(msg, f'uploading {key["name"]}')
    value = Template(files('teraflops').joinpath('key_uploader.template.sh').read_text()).safe_substitute(DESTINATION=key['path'], USER=key['user'], GROUP=key['group'], PERMISSIONS=key['permissions'], REQUIRE_OWNERSHIP='1')

    process = await asyncio.create_subprocess_exec(*ssh.cmd(deployment, ['sh', '-c', value], private_key=private_key), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate(key['text'].encode())

    if process.returncode != 0:
      console.update(msg, f'key upload failed: {stderr}', status='failure')
      raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

  console.update(msg, 'uploaded keys', status='success')

async def reboot(console, name, node, no_wait=False, private_key=None):
  async def get_boot_id(node):
    extra_args = ['-o', 'ConnectTimeout=10'] # see https://github.com/zhaofengli/colmena/issues/166#issuecomment-1892325999
    proc = await asyncio.create_subprocess_exec(*ssh.cmd(node, ['cat', '/proc/sys/kernel/random/boot_id'], private_key, extra_args), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await proc.communicate()

    return None if proc.returncode != 0 else stdout.decode()

  async def initiate_reboot(node):
    proc = await asyncio.create_subprocess_exec(*ssh.cmd(node, ['reboot'], private_key=private_key), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await proc.communicate()

    if proc.returncode == 0 or proc.returncode == 255:
      return stdout.decode()

  msg = console.message(name)

  console.update(msg, 'rebooting')

  if no_wait:
    return await initiate_reboot(node)

  old_id = await get_boot_id(node)

  await initiate_reboot(node)

  console.update(msg, 'waiting for reboot')

  while True:
    new_id = await get_boot_id(node)
    if new_id and new_id != old_id:
      break

    await asyncio.sleep(2)

  console.update(msg, 'rebooted', status='success')
