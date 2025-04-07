
import os

def opts(node):
  opts = [
    '-o',
    'StrictHostKeyChecking=accept-new',
    '-o',
    'BatchMode=yes',
    '-T'
  ]

  if os.environ.get('SSH_CONFIG_FILE'):
    opts += ['-F', os.environ['SSH_CONFIG_FILE']]

  if node.get('targetPort'):
    opts += ['-p', node['targetPort']]

  if node.get('targetUser'):
    opts += ['-l', node.get('targetUser')]

  return opts

def cmd(node, command=None, ssh_args=None):
  cmd = [
    'ssh',
    '-o',
    'StrictHostKeyChecking=accept-new',
    '-o',
    'BatchMode=yes',
  ]

  if command:
    cmd += ['-T']

  if ssh_args:
    cmd += ssh_args

  if os.environ.get('SSH_CONFIG_FILE'):
    cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

  if node.get('targetPort'):
    cmd += ['-p', node['targetPort']]

  if node.get('targetUser'):
    cmd += ['-l', node.get('targetUser')]

  cmd += [node['targetHost']]

  if command:
    cmd += command

  return cmd
