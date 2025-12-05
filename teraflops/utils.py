
import asyncio
import contextlib
import json
import os
import shutil
import tempfile

from teraflops.error import CalledProcessError
from teraflops.paths import terraform

# TODO: move me
from importlib.resources import files

eval_path = files('teraflops.nix').joinpath('eval.nix')

@contextlib.asynccontextmanager
async def generate_full_terraform_config():
  tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
  tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

  process = await asyncio.create_subprocess_exec('nix-build', '--quiet', '--no-out-link', eval_path, '-A', 'terraform', '--arg', 'flake', 'builtins.getFlake (toString ./.)', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
  stdout, stderr = await process.communicate()

  if process.returncode != 0:
    raise CalledProcessError(process.returncode, stdout, stderr)

  tf_json = stdout.strip()

  # keep a cached copy of main.tf.json
  os.makedirs(tf_data_dir, exist_ok=True)
  shutil.copy(tf_json, tf_cache_file)
  os.chmod(tf_cache_file, 0o664)

  # make main.tf.json available to terraform
  shutil.copy(tf_json, 'main.tf.json')
  os.chmod('main.tf.json', 0o664)

  try:
    yield
  finally:
    with contextlib.suppress(FileNotFoundError):
      os.remove('main.tf.json')


@contextlib.asynccontextmanager
async def generate_minimal_terraform_config(use_cache_if_available = True):
  tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
  tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

  if not os.path.isfile(tf_cache_file) or not use_cache_if_available:
    process = await asyncio.create_subprocess_exec('nix-build', '--quiet', '--no-out-link', eval_path, '-A', 'bootstrap', '--arg', 'flake', 'builtins.getFlake (toString ./.)', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
      raise CalledProcessError(process.returncode, stdout, stderr)

    tf_json = stdout.strip()

    os.makedirs(tf_data_dir, exist_ok=True)
    shutil.copy(tf_json, tf_cache_file)
    os.chmod(tf_cache_file, 0o664)

  shutil.copy(tf_cache_file, 'main.tf.json')

  try:
    yield
  finally:
    with contextlib.suppress(FileNotFoundError):
      os.remove('main.tf.json')


@contextlib.asynccontextmanager
async def generate_terraform_data_for_nix():

  async with generate_minimal_terraform_config():
    process = await asyncio.create_subprocess_exec(terraform(), 'show', '-json', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
      raise CalledProcessError(process.returncode, stdout, stderr)

  terraform_data = json.loads(stdout)
  try:
    outputs = terraform_data['values']['outputs']
    resources = terraform_data['values']['root_module']['resources']
  except KeyError:
    resources = dict()
    outputs = dict()

  resources_data = dict()
  for resource in resources:
    inner = resources_data.setdefault(resource['type'], dict())

    if resource.get('index') is not None:
      if type(resource.get('index')) == int:
        offset = int(resource.get('index'))
        index = inner.setdefault(resource['name'], list())
        index += [None] * ((offset + 1) - len(index))
        index.insert(offset, resource['values'])
      else:
        index = inner.setdefault(resource['name'], dict())
        index[resource['index']] = resource['values']
    else:
      inner[resource['name']] = resource['values']

  outputs_data = dict()
  for key, value in outputs.items():
    outputs_data[key] = value['value']

  with tempfile.TemporaryDirectory(prefix='teraflops-rewrite.', delete=True) as tempdir:
    terraform_json = os.path.join(tempdir, 'terraform.json')
    with open(terraform_json, 'w') as f:
      f.write(json.dumps(dict(outputs=outputs_data, resources=resources_data)))
      f.close()

      yield terraform_json
