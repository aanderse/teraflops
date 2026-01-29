import asyncio
import json
import os
from importlib.resources import files
from string import Template

from teraflops import ssh
from teraflops.console import Status
from teraflops.error import CalledProcessError
from teraflops.paths import flake_ref, nix

eval_path = files('teraflops.nix').joinpath('eval.nix')


async def eval(ctx, name, terraform_json):
    cmd = [
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'eval',
        '--impure',
        '--raw',
        '--expr',
        f'''
          (import {eval_path} {{
            flake = {flake_ref()};
            terraform_json = "{terraform_json}";
          }}).nodes."{name}".config.system.build.toplevel.drvPath
        ''',
    ]

    msg = ctx.message(name, f'evaluating {name}')

    env = {}
    process = await asyncio.create_subprocess_exec(
        *cmd, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stderr = b''

    while not process.stderr.at_eof():
        data = await process.stderr.readline()
        stderr += data
        line = data.decode('utf-8').rstrip()

        msg.update(line)

    stdout, _ = await process.communicate()

    if process.returncode != 0:
        lines = stderr.decode().rstrip().splitlines()
        if len(lines) > 0:
            msg.update(f'evaluation failed: {lines[-1].strip()}', status=Status.FAILURE)
        else:
            msg.update('evaluation failed: an unexpected failure occurred', status=Status.FAILURE)

        raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

    toplevel = stdout.decode().strip()
    msg.update(f'evaluated {toplevel}', status=Status.SUCCESS)
    return toplevel


async def build(ctx, name, drv):
    cmd = [
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'build',
        '--no-link',
        '--print-out-paths',
        f'{drv}^*',
    ]

    msg = ctx.message(name, f'building {name}')

    env = {}
    process = await asyncio.create_subprocess_exec(
        *cmd, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stderr = b''

    while not process.stderr.at_eof():
        data = await process.stderr.readline()
        stderr += data
        line = data.decode('utf-8').rstrip()

        msg.update(line)

    stdout, _ = await process.communicate()

    if process.returncode != 0:
        lines = stderr.decode().rstrip().splitlines()
        if len(lines) > 0:
            msg.update(f'build failed: {lines[-1].strip()}', status=Status.FAILURE)
        else:
            msg.update('build failed: an unexpected failure occurred', status=Status.FAILURE)

        raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

    toplevel = stdout.decode().strip()
    msg.update(f'built {toplevel}', status=Status.SUCCESS)

    return toplevel


async def copy(ctx, name, deployment, toplevel, private_key=None):
    cmd = [
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'copy',
        '--to',
        f'ssh-ng://{deployment["targetUser"]}@{deployment["targetHost"]}?compress=true',
        toplevel,
        '--no-check-sigs',
        '--substitute-on-destination',
        '--verbose',
    ]

    msg = ctx.message(name, 'pushing system closure')

    env = {'NIX_SSHOPTS': ' '.join(ssh.opts(deployment, private_key=private_key))}

    process = await asyncio.create_subprocess_exec(
        *cmd, env={**os.environ, **env}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stderr = b''

    while not process.stderr.at_eof():
        data = await process.stderr.readline()
        stderr += data
        line = data.decode('utf-8').rstrip()

        msg.update(line)

    await process.wait()

    if process.returncode != 0:
        lines = stderr.decode().rstrip().splitlines()
        # ctx.info(f'{name} -> len: {len(lines)}, value: "{stderr.decode()}"')
        msg.update(f'push failed: {lines[-1].strip()}', status=Status.FAILURE)

        raise CalledProcessError(process.returncode, stderr=stderr)

    msg.update('pushed system closure', status=Status.SUCCESS)


async def switch_profile(ctx, name, node, toplevel, private_key=None):
    msg = ctx.message(name, 'switching system profile')

    cmd = ssh.cmd(node, ['nix-env', '-p', '/nix/var/nix/profiles/system', '--set', toplevel], private_key=private_key)

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    stdout = b''

    while not process.stdout.at_eof():
        data = await process.stdout.readline()
        stdout += data
        line = data.decode('utf-8').rstrip()

        msg.update(line)

    _, stderr = await process.communicate()

    if process.returncode != 0:  # done, error
        msg.update(f'switching profile failed: {stderr.decode().strip()}', status=Status.FAILURE)
        raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

    msg.update('switching profile successful', status=Status.SUCCESS)


async def switch_to_configuration(ctx, name, node, toplevel, target, private_key=None):
    msg = ctx.message(name, 'activating system profile')

    cmd = ssh.cmd(node, [f'{toplevel}/bin/switch-to-configuration', target], private_key=private_key)

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    stdout = b''

    while not process.stdout.at_eof():
        data = await process.stdout.readline()
        stdout += data
        line = data.decode('utf-8').rstrip()

        msg.update(line)

    _, stderr = await process.communicate()

    if process.returncode != 0:  # done, error
        msg.update(f'activation failed: {stderr.decode().strip()}', status=Status.FAILURE)
        raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

    msg.update('activation successful', status=Status.SUCCESS)


async def upload_keys(ctx, name, deployment, terraform_json, private_key=None):
    cmd = [
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'eval',
        '--impure',
        '--json',
        '--expr',
        f'''
          (import {eval_path} {{
            flake = {flake_ref()};
            terraform_json = {terraform_json};
          }}).nodes."{name}".config.deployment.keys
        ''',
    ]

    msg = ctx.message(name, 'uploading keys')

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        msg.update(f'key upload failed: {stderr.decode().strip()}', status=Status.FAILURE)
        raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

    data = json.loads(stdout)

    for key in data.values():
        msg.update(f'uploading {key["name"]}')
        value = Template(files('teraflops').joinpath('key_uploader.template.sh').read_text()).safe_substitute(
            DESTINATION=key['path'],
            USER=key['user'],
            GROUP=key['group'],
            PERMISSIONS=key['permissions'],
            REQUIRE_OWNERSHIP='1',
        )

        process = await asyncio.create_subprocess_exec(
            *ssh.cmd(deployment, ['sh', '-c', value], private_key=private_key),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(key['text'].encode())

        if process.returncode != 0:
            msg.update(f'key upload failed: {stderr}', status=Status.FAILURE)
            raise CalledProcessError(process.returncode, stdout=stdout, stderr=stderr)

    msg.update('uploaded keys', status=Status.SUCCESS)


async def reboot(ctx, name, node, no_wait=False, private_key=None):
    async def get_boot_id(node):
        extra_args = [
            '-o',
            'ConnectTimeout=10',
        ]  # see https://github.com/zhaofengli/colmena/issues/166#issuecomment-1892325999
        proc = await asyncio.create_subprocess_exec(
            *ssh.cmd(node, ['cat', '/proc/sys/kernel/random/boot_id'], private_key, extra_args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()

        return None if proc.returncode != 0 else stdout.decode()

    async def initiate_reboot(node):
        proc = await asyncio.create_subprocess_exec(
            *ssh.cmd(node, ['reboot'], private_key=private_key),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0 or proc.returncode == 255:
            return stdout.decode()

    msg = ctx.message(name)

    msg.update('rebooting')

    if no_wait:
        return await initiate_reboot(node)

    old_id = await get_boot_id(node)

    await initiate_reboot(node)

    msg.update('waiting for reboot')

    while True:
        new_id = await get_boot_id(node)
        if new_id and new_id != old_id:
            break

        await asyncio.sleep(2)

    msg.update('rebooted', status=Status.SUCCESS)
