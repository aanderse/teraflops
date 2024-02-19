#!/usr/bin/env python3

import argparse
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
class App:
  def __init__(self, tempdir):
    self.tempdir = tempdir

  def generate_terraform_json(self):
    self.generate_main_tf_json(refresh=False)

    process = subprocess.run(['terraform', 'show', '-json'], stdout=subprocess.PIPE, check=True)
    terraform_data = json.loads(process.stdout)

    try:
      outputs = terraform_data['values']['outputs']
      resources = terraform_data['values']['root_module']['resources']
    except KeyError:
      resources = dict()
      outputs = dict()

    resources_data = dict()
    for resource in resources:
      # TODO: handle terraform
      # - [x] for_each
      # - [ ] count
      # - [ ] etc...
      inner = resources_data.setdefault(resource['type'], dict())

      if resource.get('index'):
        index = inner.setdefault(resource['name'], dict())
        index[resource['index']] = resource['values']
      else:
        inner[resource['name']] = resource['values']

    outputs_data = dict()
    for key, value in outputs.items():
      outputs_data[key] = value['value']

    with open(os.path.join(self.tempdir, 'terraform.json'), 'w') as f:
      f.write(json.dumps(dict(outputs=outputs_data, resources=resources_data), indent=2, sort_keys=True))

    return os.path.join(self.tempdir, 'terraform.json')

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
      f.write(terraform_nix)

    return os.path.join(self.tempdir, 'terraform.nix')

  # NOTE: only cache/use cached main.tf.json if no --config is specified
  def generate_main_tf_json(self, refresh: bool):
    tf_data_dir = os.getenv('TF_DATA_DIR', '.terraform')
    tf_cache_file = os.path.join(tf_data_dir, 'teraflops.json')

    if not refresh and self.config == '.' and os.path.isfile(tf_cache_file):
      shutil.copy(tf_cache_file, 'main.tf.json')
      return

    with open('main.tf.json', 'w') as f:
      cmd = ['colmena']
      if self.show_trace:
        cmd += ['--show-trace']
      cmd += ['--config', self.generate_hive_nix(full_eval=False), 'eval', self.generate_terraform_nix()]
      process = subprocess.run(cmd, stdout=subprocess.PIPE, check=True)
      json_object = json.loads(process.stdout)
      json.dump(json_object, f, indent=2)

    if self.config == '.':
      os.makedirs(tf_data_dir, exist_ok=True)
      shutil.copy('main.tf.json', tf_cache_file)

  def query_deployment(self):
    self.generate_main_tf_json(refresh=False)

    process = subprocess.run(['terraform', 'output', '-json', 'teraflops'], capture_output=True)

    try:
      output = json.loads(process.stdout)

      if 'nodes' in output:
          return output['nodes']
    except:
      pass

    process = subprocess.run(['colmena', '--config', self.generate_hive_nix(full_eval=True), 'eval', '-E', '{ nodes, pkgs, lib }: lib.mapAttrs (_: node: { inherit (node.config.deployment) tags targetHost targetPort targetUser; }) nodes'], stdout=subprocess.PIPE, check=True)
    data = json.loads(process.stdout)

    return data

  def tf(self, args):
    # needs: main.tf.json (needs: eval.nix, hive.nix, terraform.nix)

    self.generate_main_tf_json(refresh=True)
    subprocess.run(['terraform'] + args.passthru, check=True)

  def nix(self, args):
    if '--config' in args.passthru:
      logging.fatal('cannot pass through --config argument to colmena')
      sys.exit(1)

    # needs: eval.nix, hive.nix, terraform.json (needs: main.tf.json, eval.nix, hive.nix, terraform.nix)
    subprocess.run(['colmena', '--config', self.generate_hive_nix(full_eval=True)] + args.passthru, check=True)

  def init(self, args):
    self.generate_main_tf_json(refresh=True)
    subprocess.run(['terraform', 'init'], check=True)

  def repl(self, args):
    # TODO: add `resources` argument to `teraflops repl`
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'repl']
    if args.show_trace:
      cmd += ['--show-trace']
    subprocess.run(cmd, check=True)

  def eval(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'eval']
    if args.show_trace:
      cmd += ['--show-trace']
    # TODO: make `terraform` variable inaccessible from within expression
    cmd += ['-E', 'let terraform = with builtins; fromJSON (readFile %s); f = %s; in { nodes, pkgs, lib }: f { inherit nodes pkgs lib; inherit (terraform) outputs resources; }' % (os.path.join(self.tempdir, 'terraform.json'), args.expr)]
    subprocess.run(cmd, check=True)

  def eval_jobs(self, args):
    cmd = ['nix-eval-jobs', '--max-memory-size', '12000', '--workers', '12']
    if args.show_trace:
      cmd += ['--show-trace']
    cmd += ['--expr']
    cmd += ["""
    let
      colmena = builtins.getFlake "github:zhaofengli/colmena";
      eval = colmena.outputs.lib.makeHive (import %s);

      terraform = with builtins; fromJSON (readFile %s);
      f = %s;
    in
      eval.introspect ({ nodes, pkgs, lib }: f { inherit nodes pkgs lib; inherit (terraform) outputs resources; })
    """ % (self.generate_hive_nix(full_eval=True), os.path.join(self.tempdir, 'terraform.json'), args.expr)]

    subprocess.run(cmd, check=True)

  def deploy(self, args):
    self.create(args)
    self.activate(args)    

  def plan(self, args):
    self.generate_main_tf_json(refresh=True)
    subprocess.run(['terraform', 'plan'], check=True)

  def create(self, args):
    self.generate_main_tf_json(refresh=True)
    subprocess.run(['terraform', 'apply'], check=True) #check=False)

  def build(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming', '--eval-node-limit', '10', 'build']
    subprocess.run(cmd, check=True)

  def push(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming', '--eval-node-limit', '10', 'push']
    subprocess.run(cmd, check=True)

  def activate(self, args):
    cmd = ['colmena', '--config', self.generate_hive_nix(full_eval=True), 'apply']
    if args.show_trace:
      cmd += ['--show-trace']
    if args.on:
      cmd += ['--on', args.on]
    cmd += ['--evaluator', 'streaming', '--eval-node-limit', '10', 'switch']
    subprocess.run(cmd, check=True)

  def destroy(self, args):
    self.generate_main_tf_json(refresh=True)
    subprocess.run(['terraform', 'apply', '-destroy'], check=True)

  def info(self, args):
    with open(self.generate_terraform_json(), 'r') as fp:
     data = json.load(fp)
     print(json.dumps(data['resources'], indent=2))

  def check(self, args):
    nodes = self.query_deployment()

    processes = dict()
    for name, data in nodes.items():
      cmd = ['ssh']

      if os.environ.get('SSH_CONFIG_FILE'):
        cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

      if data.get('targetPort'):
        cmd += ['-p', data['targetPort']]

      if data.get('targetUser'):
        cmd += ['-l', data.get('targetUser')]

      cmd += [data['targetHost']]
      cmd += ['uptime']

      process = subprocess.Popen(cmd, stdout=subprocess.PIPE, encoding='UTF-8')

      processes[name] = process

    length = len(max(nodes.keys(), key = len)) if nodes else len('ERROR')

    for name, process in processes.items():
      rc = process.wait()

      if rc != 0:
        print(colored(name.ljust(length), color='red', attrs=['bold']), '|', colored('unavailable', color='red'))
      else:
        print(colored(name.ljust(length), color='green', attrs=['bold']), '|', colored(process.stdout.read().rstrip(), color='green'))

  def ssh(self, args):
    nodes = self.query_deployment()
    node = nodes[args.node]

    cmd = ['ssh']

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

    processes = dict()
    for name, data in nodes.items():
      cmd = ['ssh']

      if os.environ.get('SSH_CONFIG_FILE'):
        cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

      if data.get('targetPort'):
        cmd += ['-p', data['targetPort']]

      if data.get('targetUser'):
        cmd += ['-l', data.get('targetUser')]

      cmd += [data['targetHost']]
      cmd += args.command

      process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='UTF-8')

      processes[name] = process

    length = len(max(nodes.keys(), key = len)) if nodes else len('ERROR')

    for name, process in processes.items():
      rc = process.wait()

      while True:
        line = process.stdout.readline()
        if line:
          print(colored(name.ljust(length), attrs=['bold']), '|', line.rstrip())
        else:
          break

      if rc != 0:
        print(colored(name.ljust(length), color='red', attrs=['bold']), '|', colored('Failed: %s' % process.stderr.readline().rstrip(), color='red'))
      else:
        print(colored(name.ljust(length), color='green', attrs=['bold']), '|', colored('Succeeded', color='green'))

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

  def reboot(self, args):
    logging.fatal('not yet implemented')
    sys.exit(1)

  def run(self):
    parser = argparse.ArgumentParser(description='a terraform ops tool which is sure to be a flop')
    parser.add_argument('-f', '--config', default='.', help='...')
    parser.add_argument('--show-trace', action='store_true', help='passes --show-trace to nix commands')
    parser.add_argument('-q', '--quiet', action='store_true')

    on_parser = argparse.ArgumentParser(add_help=False)
    on_parser.add_argument('--on', metavar='<NODES>', help='select a list of nodes to deploy to')

    subparsers = parser.add_subparsers(title='subcommands') #, dest='subcommand')

    # subparser for the 'init' command
    init_parser = subparsers.add_parser('init', help='prepare your working directory for other commands')
    init_parser.set_defaults(func=self.init)

    # subparser for the 'repl' command
    repl_parser = subparsers.add_parser('repl', help='start an interactive REPL with the complete configuration')
    repl_parser.set_defaults(func=self.repl)

    # subparser for the 'eval' command
    eval_parser = subparsers.add_parser('eval', help='')
    eval_parser.set_defaults(func=self.eval)
    eval_parser.add_argument('expr', type=str, help='evaluate an expression using the complete configuration')

    # TODO: drop this
    # subparser for the 'eval_jobs' command
    eval_jobs_parser = subparsers.add_parser('eval-jobs')
    eval_jobs_parser.set_defaults(func=self.eval_jobs)
    eval_jobs_parser.add_argument('expr', type=str)

    # subparser for the 'deploy' command
    deploy_parser = subparsers.add_parser('deploy', help='deploy the configuration')
    deploy_parser.set_defaults(func=self.deploy)

    # subparser for the 'plan' command
    plan_parser = subparsers.add_parser('plan', help='show changes required by the current configuration')
    plan_parser.set_defaults(func=self.plan)

    # subparser for the 'create' command
    create_parser = subparsers.add_parser('create', help='create or update all resources in the deployment')
    create_parser.set_defaults(func=self.create)

    # subparser for the 'build' command
    build_parser = subparsers.add_parser('build', parents=[on_parser], help='build the system profiles')
    build_parser.set_defaults(func=self.build)

    # subparser for the 'push' command
    push_parser = subparsers.add_parser('push', parents=[on_parser], help='copy the closures to remote nodes')
    push_parser.set_defaults(func=self.push)

    # subparser for the 'activate' command
    activate_parser = subparsers.add_parser('activate', parents=[on_parser], help='apply configurations on remote nodes')
    activate_parser.set_defaults(func=self.activate)

    # subparser for the 'destroy' command
    destroy_parser = subparsers.add_parser('destroy', help='destroy all resources in the deployment')
    destroy_parser.set_defaults(func=self.destroy)

    # subparser for the 'info' command
    info_parser = subparsers.add_parser('info', help='show the state of the deployment')
    info_parser.set_defaults(func=self.info)

    # subparser for the 'check' command
    check_parser = subparsers.add_parser('check', help='attempt to connect to each node via SSH and print the results of the uptime command.')
    check_parser.set_defaults(func=self.check)

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

def main():
  handler = logging.StreamHandler()
  handler.setFormatter(ColmenaFormatter('%(message)s'))

  logging.getLogger().addHandler(handler)
  logging.getLogger().setLevel(logging.INFO) # TODO: observe RUST_LOG environment variable, --verbose + --quiet

  with tempfile.TemporaryDirectory(prefix='teraflops.', delete=True) as tempdir:
    app = App(tempdir)
    app.run()

if __name__ == '__main__':
  main()
