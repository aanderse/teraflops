
import subprocess
import os

from teraflops import nodes

async def run(args):
  output_data = await nodes.get_teraflops_data()

  cmd = ['scp']

  if args.r:
    cmd += ['-r']

  if os.environ.get('SSH_CONFIG_FILE'):
    cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

  source = args.source
  target = args.target

  if ':' in args.source:
    source_machine, _, source_path = args.source.partition(':')

    node = output_data['nodes'][source_machine]

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

    node = output_data['nodes'][target_machine]

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

  subprocess.run(cmd)

def register_action(subparsers):
  parser = subparsers.add_parser('scp', help='copy files to or from the specified machine via scp')
  parser.set_defaults(func=run)
  parser.add_argument('-r', action='store_true', help='recursively copy entire directories')
  parser.add_argument('source', type=str, help='source file location')
  parser.add_argument('target', type=str, help='destination file location')
