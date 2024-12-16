#!/usr/bin/env python3

import argparse
import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

from importlib.resources import files
from termcolor import colored

class ColmenaFormatter(logging.Formatter):
  _prefix = {
      logging.FATAL: colored('FATAL', color='red', attrs=['bold']),
      logging.ERROR: 'ERROR',
      logging.WARNING: colored('WARN ', color='yellow'),
      logging.INFO: colored('INFO ', color='green'),
      logging.DEBUG: 'DEBUG',
      logging.NOTSET: '',
  }

  def format(self, record):
    return '[' + self._prefix[record.levelno] + '] ' + super().format(record)

# adapted from https://github.com/zhaofengli/colmena/blob/main/src/nix/node_filter.rs
class NodeFilter:
  def __init__(self, filter_str):
    trimmed = filter_str.strip()
    if not trimmed:
      logging.warning(f'Filter "{filter_str}" is blank and will match nothing')
      self.rules = []
      return

    self.rules = [
      Rule(pattern.strip('@') if pattern.startswith('@') else pattern)
      for pattern in trimmed.split(',')
    ]

  def filter(self, nodes):
    if not self.rules:
      return dict()

    result = dict()
    for name, node in nodes.items():
      for rule in self.rules:
        if rule.matches_name(name):
          result[name] = node
        elif rule.matches_tag(node['tags']):
          result[name] = node

    return result

class Rule:
  def __init__(self, pattern):
    self.pattern = pattern

  def matches_name(self, name):
    return re.match(self.pattern, name) is not None

  def matches_tag(self, tags):
    return any(re.match(self.pattern, tag) for tag in tags)

def ssh_config(private_key, tempdir):
  ssh_config_file = os.path.join(tempdir, '.ssh', 'config')
  private_key_file = os.path.join(tempdir, '.ssh', 'id_ed25519')

  os.makedirs(os.path.join(tempdir, '.ssh'), mode=0o700)

  with open(private_key_file, mode="w", opener=lambda path, flags: os.open(path, flags, 0o600)) as fp:
    fp.write(private_key)

  with open(ssh_config_file, mode="w") as fp:
    # ConnectTimeout: see https://github.com/zhaofengli/colmena/issues/166#issuecomment-1892325999
    fp.write('Host *\n  ConnectTimeout=10s\n  IdentityFile %s' % private_key_file)

  os.environ['SSH_CONFIG_FILE'] = ssh_config_file

def ssh(node, command, ssh_args=None):
  cmd = ['ssh',
    '-o',
    'StrictHostKeyChecking=accept-new',
    '-o',
    'BatchMode=yes',
    '-T',
  ]

  if ssh_args:
    cmd += ssh_args

  if os.environ.get('SSH_CONFIG_FILE'):
    cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

  if node.get('targetPort'):
    cmd += ['-p', node['targetPort']]

  if node.get('targetUser'):
    cmd += ['-l', node.get('targetUser')]

  cmd += [node['targetHost']]
  cmd += command

  return cmd

class App:
  def __init__(self, tempdir):
    self.tempdir = tempdir
    self.teraflops_arguments = dict()

  def generate_arguments_json(self):
    tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
    tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

    # if we already have a cached .tf.json file don't bother generating one
    if self.config == '.' and os.path.isfile(tf_cache_file):
      shutil.copy(tf_cache_file, 'main.tf.json')

      process = subprocess.run([self.terraform, 'show', '-json'], stdout=subprocess.PIPE, check=True)
      data = json.loads(process.stdout)

      with contextlib.suppress(FileNotFoundError):
        os.remove('main.tf.json')
    else:
      with tempfile.NamedTemporaryFile(mode='w', dir=os.getcwd(), prefix='teraflops', suffix='.tf.json') as fp:
        # generate a minimal .tf.json file which can be used to run 'terraform show -json'
        subprocess.run(['nix-instantiate', '--eval', '--json', '--strict', '--read-write-mode', self.generate_bootstrap_nix()], stdout=fp, check=True)

        process = subprocess.run([self.terraform, 'show', '-json'], stdout=subprocess.PIPE, check=True)
        data = json.loads(process.stdout)

    try:
      resources = data['values']['root_module']['resources']
      for resource in resources:
        if resource['address'] == 'terraform_data.teraflops-arguments':
          self.teraflops_arguments = resource['values']['input']
    except KeyError:
      pass

    with open(os.path.join(self.tempdir, 'arguments.json'), 'w') as fp:
      fp.write(json.dumps(self.teraflops_arguments, indent=2, sort_keys=True))

  def generate_terraform_json(self, need_tf_file=True):
    if need_tf_file:
      self.generate_main_tf_json(refresh=False)

    process = subprocess.run([self.terraform, 'show', '-json'], stdout=subprocess.PIPE, check=True)
    terraform_data = json.loads(process.stdout)

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

    with open(os.path.join(self.tempdir, 'terraform.json'), 'w') as f:
      f.write(json.dumps(dict(outputs=outputs_data, resources=resources_data), indent=2, sort_keys=True))

    if not os.environ.get('SSH_CONFIG_FILE'):
      try:
        private_key = outputs['teraflops']['value']['privateKey']
      except KeyError:
        private_key = None

      if private_key is not None:
        ssh_config(private_key, self.tempdir)

    return os.path.join(self.tempdir, 'terraform.json')

  def generate_bootstrap_nix(self):
    process = subprocess.run(['nix', '--extra-experimental-features', 'nix-command', 'flake', 'metadata', '--json', self.config], stdout=subprocess.PIPE, check=True)
    metadata = json.loads(process.stdout)

    flake = metadata['resolvedUrl']

    bootstrap_nix = files('teraflops.nix').joinpath('bootstrap.nix').read_text()

    with open(os.path.join(self.tempdir, 'bootstrap.nix'), 'w') as f:
      f.write(bootstrap_nix % flake)

    return os.path.join(self.tempdir, 'bootstrap.nix')

  def generate_eval_nix(self):
    process = subprocess.run(['nix', '--extra-experimental-features', 'nix-command', 'flake', 'metadata', '--json', self.config], stdout=subprocess.PIPE, check=True)
    metadata = json.loads(process.stdout)

    flake = metadata['resolvedUrl']

    eval_nix = files('teraflops.nix').joinpath('eval.nix').read_text()

    with open(os.path.join(self.tempdir, 'eval.nix'), 'w') as f:
      f.write(eval_nix % flake)

  def generate_hive_nix(self, full_eval: bool):
    if full_eval:
      self.generate_terraform_json()

    hive_nix = files('teraflops.nix').joinpath('hive.nix').read_text()

    with open(os.path.join(self.tempdir, 'hive.nix'), 'w') as f:
      f.write(hive_nix)
    
    return os.path.join(self.tempdir, 'hive.nix')

  def generate_terraform_nix(self):
    terraform_nix = files('teraflops.nix').joinpath('terraform.nix').read_text()

    with open(os.path.join(self.tempdir, 'terraform.nix'), 'w') as f:
      f.write(terraform_nix % files('teraflops.nix').joinpath('colmena'))

    return os.path.join(self.tempdir, 'terraform.nix')

  def generate_repl_nix(self):
    repl_nix = files('teraflops.nix').joinpath('repl.nix').read_text()

    with open(os.path.join(self.tempdir, 'repl.nix'), 'w') as f:
      f.write(repl_nix % files('teraflops.nix').joinpath('colmena'))

    return os.path.join(self.tempdir, 'repl.nix')

  # NOTE: only cache/use cached main.tf.json if no --config is specified
  def generate_main_tf_json(self, refresh: bool, rewrite_args=False):
    tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
    tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

    if not refresh and self.config == '.' and os.path.isfile(tf_cache_file):
      if rewrite_args:
        with open(tf_cache_file, 'r') as fp:
          data = json.load(fp)

        data.setdefault('resource', dict())
        data['resource'].setdefault('terraform_data', dict())
        data['resource']['terraform_data'].setdefault('teraflops-arguments', dict())
        data['resource']['terraform_data']['teraflops-arguments'].setdefault('input', dict())
        data['resource']['terraform_data']['teraflops-arguments']['input'] = self.teraflops_arguments

        with open('main.tf.json', 'w') as fp:
          json.dump(data, fp, indent=2)
      else:
        shutil.copy(tf_cache_file, 'main.tf.json')
      return

    self.generate_hive_nix(full_eval=False)

    cmd = ['nix-build', '--quiet']
    if self.show_trace:
      cmd += ['--show-trace']
    cmd += ['--out-link', 'main.tf.json', self.generate_terraform_nix()]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, check=True)

    if self.config == '.':
      os.makedirs(tf_data_dir, exist_ok=True)
      shutil.copy('main.tf.json', tf_cache_file)
      os.chmod(tf_cache_file, 0o664)

  def query_deployment(self, need_tf_file=True):
    if need_tf_file:
      self.generate_main_tf_json(refresh=False)

    process = subprocess.run([self.terraform, 'output', '-json', 'teraflops'], capture_output=True)

    with contextlib.suppress(FileNotFoundError):
      os.remove('main.tf.json')

    try:
      output = json.loads(process.stdout)
    except:
      process = subprocess.run(['colmena', '--config', self.generate_hive_nix(full_eval=True), 'eval', '-E', '{ nodes, pkgs, lib }: { privateKey = null; nodes = lib.mapAttrs (_: node: { inherit (node.config.deployment) provisionSSHKey tags targetEnv targetHost targetPort targetUser; }) nodes; }'], stdout=subprocess.PIPE, check=True)
      output = json.loads(process.stdout)

    if not os.environ.get('SSH_CONFIG_FILE'):
      try:
        private_key = output['privateKey']
      except KeyError:
        private_key = None

      if private_key is not None:
        ssh_config(private_key, self.tempdir)

    return output['nodes']

  def tf(self, args):
    self.generate_main_tf_json(refresh=True)
    subprocess.run([self.terraform] + args.passthru, check=True)

  def nix(self, args):
    if '--config' in args.passthru:
      logging.fatal('cannot pass through --config argument to colmena')
      sys.exit(1)

    subprocess.run(['colmena', '--config', self.generate_hive_nix(full_eval=True)] + args.passthru, check=True)

  def init(self, args):
    cmd = [self.terraform, 'init']
    if args.migrate_state:
      cmd += ['-migrate-state']
    if args.reconfigure:
      cmd += ['-reconfigure']
    if args.upgrade:
      cmd += ['-upgrade']

    with tempfile.NamedTemporaryFile(mode='w', dir=os.getcwd(), prefix='teraflops', suffix='.tf.json') as fp:
      # generate a minimal .tf.json file which can be used to run 'terraform init'
      subprocess.run(['nix-instantiate', '--eval', '--json', '--strict', '--read-write-mode', self.generate_bootstrap_nix()], stdout=fp, check=True)
      subprocess.run(cmd, check=True)

  def repl(self, args):
    self.generate_hive_nix(full_eval=True)
    cmd = ['nix', 'repl']
    cmd += ['--experimental-features', 'nix-command flakes']
    if args.show_trace:
      cmd += ['--show-trace']
    # if nix_version.at_least(2, 10):
    cmd += ['--file', self.generate_repl_nix()]

    with contextlib.suppress(FileNotFoundError):
      os.remove('main.tf.json')

    subprocess.run(cmd, check=True)

  def eval(self, args):
    hive_nix = self.generate_hive_nix(full_eval=True)

    async def colmena_eval(expr):
      cmd = ['colmena', '--config', hive_nix, 'eval']
      if args.show_trace:
        cmd += ['--show-trace']
      # TODO: make `terraform` variable inaccessible from within expression
      cmd += ['-E', 'let terraform = with builtins; fromJSON (readFile %s); arguments = with builtins; fromJSON (readFile %s); f = %s; in { nodes, pkgs, lib }: f ({ inherit nodes pkgs lib; inherit (terraform) outputs resources; } // arguments)' % (os.path.join(self.tempdir, 'terraform.json'), os.path.join(self.tempdir, 'arguments.json'), expr)]

      process = await asyncio.create_subprocess_exec(*cmd)
      _, _ = await process.communicate()

      if process.returncode != 0:
        raise Exception(process.stderr)

    async def run():
      try:
        async with asyncio.TaskGroup() as tg:
          tasks = [tg.create_task(colmena_eval(expr)) for expr in args.expr]
      except:
        sys.exit(1)

    asyncio.run(run())

  def deploy(self, args):
    # apply
    self.generate_main_tf_json(refresh=True)

    cmd = [self.terraform, 'apply']
    if args.confirm:
      cmd += ['-auto-approve']

    subprocess.run(cmd, check=True)

    self.generate_terraform_json(need_tf_file=False)


    # make sure all relevant nodes are available
    nodes = self.query_deployment(need_tf_file=False)

    if not (args.on is None):
      node_filter = NodeFilter(args.on)
      nodes = node_filter.filter(nodes)

    length = len(max(nodes.keys(), key = len)) if nodes else len('ERROR')

    ssh_args = ['-o', 'ConnectTimeout=10'] # see https://github.com/zhaofengli/colmena/issues/166#issuecomment-1892325999

    async def wait_for_node(name, node):
      # TODO: mimic colmena spinners to let user know that we're waiting for nodes to become available
      while True:
        proc = await asyncio.create_subprocess_exec(*ssh(node, ['cat', '/proc/sys/kernel/random/boot_id'], ssh_args), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)

        if await proc.wait() == 0:
          break

        await asyncio.sleep(2)

    async def run():
      tasks = [wait_for_node(name, node) for name, node in nodes.items()]
      return await asyncio.gather(*tasks)

    asyncio.run(run())


    # activate
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=False), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.verbose:
      cmd += ['--verbose']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming']
    if not (args.eval_node_limit is None):
      cmd += ['--eval-node-limit', str(args.eval_node_limit)]
    if not (args.parallel is None):
      cmd += ['--parallel', str(args.parallel)]
    if args.reboot:
      cmd += ['boot', '--reboot']
    else:
      cmd += ['switch']

    subprocess.run(cmd, check=True)

  def plan(self, args):
    self.generate_main_tf_json(refresh=True)
    subprocess.run([self.terraform, 'plan'], check=True)

  def apply(self, args):
    self.generate_main_tf_json(refresh=True)

    cmd = [self.terraform, 'apply']
    if args.confirm:
      cmd += ['-auto-approve']

    subprocess.run(cmd, check=True)

  def build(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.verbose:
      cmd += ['--verbose']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming']
    if not (args.eval_node_limit is None):
      cmd += ['--eval-node-limit', str(args.eval_node_limit)]
    cmd += ['build']
    subprocess.run(cmd, check=True)

  def push(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.verbose:
      cmd += ['--verbose']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming']
    if not (args.eval_node_limit is None):
      cmd += ['--eval-node-limit', str(args.eval_node_limit)]
    if not (args.parallel is None):
      cmd += ['--parallel', str(args.parallel)]
    cmd += ['push']
    subprocess.run(cmd, check=True)

  def activate(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.verbose:
      cmd += ['--verbose']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming']
    if not (args.eval_node_limit is None):
      cmd += ['--eval-node-limit', str(args.eval_node_limit)]
    if not (args.parallel is None):
      cmd += ['--parallel', str(args.parallel)]
    if args.reboot:
      cmd += ['boot', '--reboot']
    else:
      cmd += ['switch']
    subprocess.run(cmd, check=True)

  def destroy(self, args):
    self.generate_main_tf_json(refresh=True)

    cmd = [self.terraform, 'apply', '-destroy']
    if args.confirm:
      cmd += ['-auto-approve']

    subprocess.run(cmd, check=True)

  def info(self, args):
    with open(self.generate_terraform_json(), 'r') as fp:
      data = json.load(fp)

    # filter out internal state

    try:
      del data['resources']['tls_private_key']['teraflops']
      if not data['resources']['tls_private_key']:
        del data['resources']['tls_private_key']
    except KeyError:
      pass

    try:
      del data['resources']['terraform_data']['teraflops-arguments']
      if not data['resources']['terraform_data']:
        del data['resources']['terraform_data']
    except KeyError:
      pass

    print(json.dumps(data['resources'], indent=2))

  def check(self, args):
    nodes = self.query_deployment()

    length = len(max(nodes.keys(), key = len)) if nodes else len('ERROR')

    async def uptime(name, node):
      process = await asyncio.create_subprocess_exec(*ssh(node, ['uptime']), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
      stdout, _ = await process.communicate()

      if process.returncode != 0:
        print(colored(name.ljust(length), color='red', attrs=['bold']), '|', colored('unavailable', color='red'))
      else:
        print(colored(name.ljust(length), color='green', attrs=['bold']), '|', colored(stdout.decode().rstrip(), color='green'))

    async def run():
      tasks = [uptime(name, node) for name, node in nodes.items()]
      return await asyncio.gather(*tasks)

    asyncio.run(run())

  def set_args(self, args):
    if args.arg:
      for (name, value) in args.arg:
        new_value = json.loads(subprocess.check_output(['nix', '--extra-experimental-features', 'nix-command', 'eval', '--json', '--expr', '%s' % value]))
        self.teraflops_arguments[name] = new_value

    if args.argstr:
      for (name, value) in args.argstr:
        self.teraflops_arguments[name] = value

    if args.unset:
      for name in args.unset:
        if name in self.teraflops_arguments: del self.teraflops_arguments[name]

    with open(os.path.join(self.tempdir, 'arguments.json'), 'w') as fp:
      fp.write(json.dumps(self.teraflops_arguments, indent=2, sort_keys=True))

    self.generate_main_tf_json(refresh=False, rewrite_args=True)

    subprocess.run([self.terraform, 'apply', '-target=terraform_data.teraflops-arguments', '-auto-approve'], stdout=subprocess.DEVNULL, check=True)

  def show_args(self, args):
    if args.json:
      print(json.dumps(self.teraflops_arguments, indent=2, sort_keys=True))
    else:
      for k, v in self.teraflops_arguments.items():
        if type(v) == str:
          print(f'{k} = "{v}"')
        else:
          print(f'{k} = {v}')

  def ssh(self, args):
    nodes = self.query_deployment()
    node = nodes[args.node]

    cmd = ['ssh',
      '-o',
      'StrictHostKeyChecking=accept-new',
      '-o',
      'BatchMode=yes',
    ]

    if os.environ.get('SSH_CONFIG_FILE'):
      cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

    if node.get('targetPort'):
      cmd += ['-p', node['targetPort']]

    if node.get('targetUser'):
      cmd += ['-l', node.get('targetUser')]

    cmd += [node['targetHost']]

    subprocess.run(cmd, check=True)

  def ssh_for_each(self, args):
    nodes = self.query_deployment()
    count = len(nodes)

    if not (args.on is None):
      node_filter = NodeFilter(args.on)
      nodes = node_filter.filter(nodes)

    logging.info('Enumerating nodes..')

    if nodes:
      logging.info(f'Selected {len(nodes)} out of {count} hosts.')
    else:
      logging.warning('No hosts selected (0 skipped).')

    length = len(max(nodes.keys(), key = len)) if nodes else len('ERROR')

    async def execute(name, node):
      process = await asyncio.create_subprocess_exec(*ssh(node, args.command), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
      stdout, stderr = await process.communicate()

      for line in stdout.decode().splitlines():
        print(colored(name.ljust(length), attrs=['bold']), '|', line.rstrip())

      if process.returncode == 0:
        return stdout.decode()

      if process.returncode != 0:
        print(colored(name.ljust(length), color='red', attrs=['bold']), '|', colored('Failed: %s' % stderr.decode().rstrip(), color='red'))
      else:
        print(colored(name.ljust(length), color='green', attrs=['bold']), '|', colored('Succeeded', color='green'))

    async def run():
      tasks = [execute(name, node) for name, node in nodes.items()]
      return await asyncio.gather(*tasks)

    asyncio.run(run())
    print(''.ljust(length), '|', colored('All done!', color='green'))

  def scp(self, args):
    nodes = self.query_deployment()

    cmd = ['scp']

    if args.r:
      cmd += ['-r']

    if os.environ.get('SSH_CONFIG_FILE'):
      cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

    source = args.source
    target = args.target

    if ':' in args.source:
      source_machine, _, source_path = args.source.partition(':')

      node = nodes[source_machine]

      if node.get('targetPort'):
        cmd += ['-P', node['targetPort']]

      source = ''
      if node.get('targetUser'):
        source += node.get('targetUser')
        source += '@'
      if ':' in node['targetHost']:
        source += '['
        source += node['targetHost']
        source += ']'
      else:
        source += node['targetHost']
      source += ':'
      source += source_path

    if ':' in args.target:
      target_machine, _, target_path = args.target.partition(':')

      node = nodes[target_machine]

      if node.get('targetPort'):
        cmd += ['-P', node['targetPort']]

      target = ''
      if node.get('targetUser'):
        target += node.get('targetUser')
        target += '@'
      if ':' in node['targetHost']:
        target += '['
        target += node['targetHost']
        target += ']'
      else:
        target += node['targetHost']
      target += ':'
      target += target_path

    cmd += [source, target]

    subprocess.run(cmd, check=True)

  # adapted from https://github.com/zhaofengli/colmena/blob/main/src/nix/host/ssh.rs
  # TODO: it would be nice to get a 'reboot' command right into colmena
  def reboot(self, args):
    # TODO: error handling

    nodes = self.query_deployment()
    count = len(nodes)

    if not (args.on is None):
      node_filter = NodeFilter(args.on)
      nodes = node_filter.filter(nodes)

    logging.info('Enumerating nodes..')

    if nodes:
      logging.info(f'Selected {len(nodes)} out of {count} hosts.')
    else:
      logging.warning('No hosts selected (0 skipped).')

    length = len(max(nodes.keys(), key = len)) if nodes else len('ERROR')

    async def get_boot_id(node):
      ssh_args = ['-o', 'ConnectTimeout=10'] # see https://github.com/zhaofengli/colmena/issues/166#issuecomment-1892325999
      proc = await asyncio.create_subprocess_exec(*ssh(node, ['cat', '/proc/sys/kernel/random/boot_id'], ssh_args), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
      stdout, _ = await proc.communicate()

      return None if proc.returncode != 0 else stdout.decode()

    async def initiate_reboot(node):
      proc = await asyncio.create_subprocess_exec(*ssh(node, ['reboot']), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
      stdout, _ = await proc.communicate()

      if proc.returncode == 0 or proc.returncode == 255:
        return stdout.decode()

    async def reboot(name, node):
      print(colored(name.ljust(length), attrs=['bold']), '| Rebooting')

      if args.no_wait:
        return await initiate_reboot(node)

      old_id = await get_boot_id(node)

      await initiate_reboot(node)

      print(colored(name.ljust(length), attrs=['bold']), '| Waiting for reboot')

      while True:
        new_id = await get_boot_id(node)
        if new_id and new_id != old_id:
          break

        await asyncio.sleep(2)

      print(colored(name.ljust(length), color='green', attrs=['bold']), '|', colored('Rebooted', color='green'))

    async def run():
      tasks = [reboot(name, node) for name, node in nodes.items()]
      return await asyncio.gather(*tasks)

    asyncio.run(run())
    print(''.ljust(length), '|', colored('All done!', color='green'))

  def run(self):
    parser = argparse.ArgumentParser(description='a terraform ops tool which is sure to be a flop')
    parser.add_argument('-f', '--config', default='.', help='...')
    parser.add_argument('--show-trace', action='store_true', help='passes --show-trace to nix commands')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')

    confirm_parser = argparse.ArgumentParser(add_help=False)
    confirm_parser.add_argument('--confirm', action='store_true', help='confirm dangerous operations; do not ask')

    on_parser = argparse.ArgumentParser(add_help=False)
    on_parser.add_argument('--on', metavar='<NODES>', help='select a list of nodes to deploy to')

    eval_node_limit_parser = argparse.ArgumentParser(add_help=False)
    eval_node_limit_parser.add_argument('--eval-node-limit', metavar='<LIMIT>', type=int, help='limits the maximum number of hosts to be evaluated at once')

    parallel_parser = argparse.ArgumentParser(add_help=False)
    parallel_parser.add_argument('--parallel', metavar='<LIMIT>', type=int, help='limits the maximum number of hosts to be deployed in parallel')

    subparsers = parser.add_subparsers(title='subcommands') #, dest='subcommand')

    # subparser for the 'init' command
    init_parser = subparsers.add_parser('init', help='prepare your working directory for other commands')
    init_parser.set_defaults(func=self.init)
    init_parser.add_argument('--migrate-state', action='store_true', help='reconfigure a backend, and attempt to migrate any existing state')
    init_parser.add_argument('--reconfigure', action='store_true', help='reconfigure a backend, ignoring any saved configuration')
    init_parser.add_argument('--upgrade', action='store_true', help='install the latest module and provider versions allowed within configured constraints, overriding the default behavior of selecting exactly the version recorded in the dependency lockfile.')

    # subparser for the 'repl' command
    repl_parser = subparsers.add_parser('repl', help='start an interactive REPL with the complete configuration')
    repl_parser.set_defaults(func=self.repl)

    # subparser for the 'eval' command
    eval_parser = subparsers.add_parser('eval', help='evaluate an expression using the complete configuration')
    eval_parser.set_defaults(func=self.eval)
    eval_parser.add_argument('expr', nargs='+', type=str, help='the nix expression(s) to evaluate')

    # subparser for the 'deploy' command
    deploy_parser = subparsers.add_parser('deploy', parents=[confirm_parser, on_parser, eval_node_limit_parser, parallel_parser], help='deploy the configuration')
    deploy_parser.set_defaults(func=self.deploy)
    deploy_parser.add_argument('--reboot', action='store_true', help='reboots nodes after activation and waits for them to come back up')

    # subparser for the 'plan' command
    plan_parser = subparsers.add_parser('plan', help='show changes required by the current configuration')
    plan_parser.set_defaults(func=self.plan)

    # subparser for the 'apply' command
    apply_parser = subparsers.add_parser('apply', parents=[confirm_parser], help='create or update all resources in the deployment')
    apply_parser.set_defaults(func=self.apply)

    # subparser for the 'build' command
    build_parser = subparsers.add_parser('build', parents=[on_parser, eval_node_limit_parser], help='build the system profiles')
    build_parser.set_defaults(func=self.build)

    # subparser for the 'push' command
    push_parser = subparsers.add_parser('push', parents=[on_parser, eval_node_limit_parser, parallel_parser], help='copy the closures to remote nodes')
    push_parser.set_defaults(func=self.push)

    # subparser for the 'activate' command
    activate_parser = subparsers.add_parser('activate', parents=[on_parser, eval_node_limit_parser, parallel_parser], help='apply configurations on remote nodes')
    activate_parser.set_defaults(func=self.activate)
    activate_parser.add_argument('--reboot', action='store_true', help='reboots nodes after activation and waits for them to come back up')

    # subparser for the 'destroy' command
    destroy_parser = subparsers.add_parser('destroy', parents=[confirm_parser], help='destroy all resources in the deployment')
    destroy_parser.set_defaults(func=self.destroy)

    # subparser for the 'info' command
    info_parser = subparsers.add_parser('info', help='show the state of the deployment')
    info_parser.set_defaults(func=self.info)

    # subparser for the 'check' command
    check_parser = subparsers.add_parser('check', help='attempt to connect to each node via SSH and print the results of the uptime command.')
    check_parser.set_defaults(func=self.check)

    # subparser for the 'set-args' command
    set_args_parser = subparsers.add_parser('set-args', help='persistently sets arguments to be passed to the deployment specification')
    set_args_parser.set_defaults(func=self.set_args)
    set_args_parser.add_argument('--arg', nargs=2, action='append', metavar=('name', 'value'), help='set the function argument name to value, where the latter is an arbitrary nix expression')
    set_args_parser.add_argument('--argstr', nargs=2, action='append', metavar=('name', 'value'), help='like --arg, but the value is a literal string rather than a nix expression')
    set_args_parser.add_argument('--unset', action='append', metavar='name', help='remove a previously set function argument')

    # subparser for the 'show-args' command
    show_args_parser = subparsers.add_parser('show-args', aliases=['show-arguments'], help='print the arguments to be passed to the deployment')
    show_args_parser.set_defaults(func=self.show_args)
    show_args_parser.add_argument('--json', action='store_true')

    # subparser for the 'ssh' command
    ssh_parser = subparsers.add_parser('ssh', help='login on the specified machine via SSH')
    ssh_parser.set_defaults(func=self.ssh)
    ssh_parser.add_argument('node', type=str, help='identifier of the node')

    # subparser for the 'ssh_for_each' command
    ssh_for_each_parser = subparsers.add_parser('ssh-for-each', parents=[on_parser], help='execute a command on each machine via SSH')
    ssh_for_each_parser.set_defaults(func=self.ssh_for_each)
    ssh_for_each_parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run')

    # subparser for the 'scp' command
    scp_parser = subparsers.add_parser('scp', help='copy files to or from the specified machine via scp')
    scp_parser.set_defaults(func=self.scp)
    scp_parser.add_argument('-r', action='store_true', help='recursively copy entire directories')
    scp_parser.add_argument('source', type=str, help='source file location')
    scp_parser.add_argument('target', type=str, help='destination file location')

    reboot_parser = subparsers.add_parser('reboot', parents=[on_parser], help='reboot all nodes in the deployment')
    reboot_parser.set_defaults(func=self.reboot)
    reboot_parser.add_argument('--no-wait', action='store_true', help='do not wait until the nodes are up again')


    # TODO: different subparser

    # subparser for the 'tf' command
    tf_parser = subparsers.add_parser('tf', help='low level terraform commands')
    tf_parser.set_defaults(func=self.tf)
    tf_parser.add_argument('passthru', nargs=argparse.REMAINDER)

    # subparser for the 'nix' command
    nix_parser = subparsers.add_parser('nix', help='low level colmena commands')
    nix_parser.set_defaults(func=self.nix)
    nix_parser.add_argument('passthru', nargs=argparse.REMAINDER)


    # parse the command-line arguments
    args = parser.parse_args()

    # call the appropriate function based on the subcommand
    if hasattr(args, 'func'):
      try:
        self.config = args.config
        self.show_trace = args.show_trace

        # 'init' is the only function which doesn't require arguments... all it does is prep the directory
        if args.func != self.init:
          self.generate_arguments_json()

        self.generate_eval_nix()

        args.func(args)
      except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
      finally:
        with contextlib.suppress(FileNotFoundError):
          os.remove('main.tf.json')
    else:
      # if no subcommand is provided, print help
      parser.print_help()

  def check_version(self):
    # run various checks to ensure we're in a good state to proceed
    if shutil.which('terraform'):
      self.terraform = 'terraform'
    elif shutil.which('tofu'):
      self.terraform = 'tofu'
    else:
      logging.error('terraform doesn\'t appear to be installed')
      sys.exit(1)

    if not shutil.which('colmena'):
      logging.error('colmena doesn\'t appear to be installed')
      sys.exit(1)

def main():
  try:
    handler = logging.StreamHandler()
    handler.setFormatter(ColmenaFormatter('%(message)s'))

    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO) # TODO: observe RUST_LOG environment variable, --verbose + --quiet

    with tempfile.TemporaryDirectory(prefix='teraflops.', delete=True) as tempdir:
      app = App(tempdir)
      app.check_version()
      app.run()
  except KeyboardInterrupt:
    try:
      sys.exit(130)
    except SystemExit:
      os._exit(130)

if __name__ == '__main__':
  main()
