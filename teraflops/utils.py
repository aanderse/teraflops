import asyncio
import contextlib
import json
import os
import shutil
import tempfile

# TODO: move me
from importlib.resources import files

from teraflops.error import CalledProcessError
from teraflops.paths import flake_ref, nix, terraform, terraform_config_file

eval_path = files('teraflops.nix').joinpath('eval.nix')


@contextlib.asynccontextmanager
async def generate_full_terraform_config():
    tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
    tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

    process = await asyncio.create_subprocess_exec(
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'build',
        '--no-link',
        '--print-out-paths',
        '--impure',
        '--expr',
        f'(import {eval_path} {{ flake = {flake_ref()}; }}).terraform',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise CalledProcessError(process.returncode, stdout, stderr)

    tf_json = stdout.strip()

    # keep a cached copy of the terraform config
    os.makedirs(tf_data_dir, exist_ok=True)
    shutil.copy(tf_json, tf_cache_file)
    os.chmod(tf_cache_file, 0o664)

    # make terraform config available to terraform
    config_file = terraform_config_file()
    shutil.copy(tf_json, config_file)
    os.chmod(config_file, 0o664)

    try:
        yield config_file
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(config_file)


@contextlib.asynccontextmanager
async def generate_minimal_terraform_config(use_cache_if_available=True):
    tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
    tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

    if not os.path.isfile(tf_cache_file) or not use_cache_if_available:
        process = await asyncio.create_subprocess_exec(
            nix(),
            '--extra-experimental-features',
            'flakes nix-command',
            'build',
            '--no-link',
            '--print-out-paths',
            '--impure',
            '--expr',
            f'(import {eval_path} {{ flake = {flake_ref()}; }}).bootstrap',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, stdout, stderr)

        tf_json = stdout.strip()

        os.makedirs(tf_data_dir, exist_ok=True)
        shutil.copy(tf_json, tf_cache_file)
        os.chmod(tf_cache_file, 0o664)

    config_file = terraform_config_file()
    shutil.copy(tf_cache_file, config_file)

    try:
        yield config_file
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(config_file)


@contextlib.asynccontextmanager
async def generate_terraform_data_for_nix():
    async with generate_minimal_terraform_config():
        process = await asyncio.create_subprocess_exec(
            terraform(), 'show', '-json', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, stdout, stderr)

    terraform_data = json.loads(stdout)
    try:
        outputs = terraform_data['values']['outputs']
        resources = terraform_data['values']['root_module']['resources']
    except KeyError:
        resources = {}
        outputs = {}

    resources_data = {}
    for resource in resources:
        inner = resources_data.setdefault(resource['type'], {})

        if resource.get('index') is not None:
            if isinstance(resource.get('index'), int):
                offset = int(resource.get('index'))
                index = inner.setdefault(resource['name'], [])
                index += [None] * ((offset + 1) - len(index))
                index.insert(offset, resource['values'])
            else:
                index = inner.setdefault(resource['name'], {})
                index[resource['index']] = resource['values']
        else:
            inner[resource['name']] = resource['values']

    outputs_data = {}
    for key, value in outputs.items():
        outputs_data[key] = value['value']

    with tempfile.TemporaryDirectory(prefix='teraflops-rewrite.', delete=True) as tempdir:
        terraform_json = os.path.join(tempdir, 'terraform.json')
        with open(terraform_json, 'w') as f:
            f.write(json.dumps({'outputs': outputs_data, 'resources': resources_data}))
            f.close()

            yield terraform_json
