#!/usr/bin/env python3

import argparse
import asyncio
import codecs

import importlib
import os
import subprocess
import sys

async def main():

  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbose', action='store_true')

  confirm_parser = argparse.ArgumentParser(add_help=False)
  confirm_parser.add_argument('--confirm', action='store_true', help='confirm dangerous operations; do not ask')

  on_parser = argparse.ArgumentParser(add_help=False)
  on_parser.add_argument('--on', metavar='<NODES>', help='select a list of nodes to deploy to')

  no_keys_parser = argparse.ArgumentParser(add_help=False)
  no_keys_parser.add_argument('--no-keys', action='store_true', help='do not upload secret keys set in `deployment.keys`')

  with_drvs = argparse.ArgumentParser(add_help=False)
  with_drvs.add_argument('--with-drvs', metavar='<FILE>', help='a file including json key value pairs of node name and the associated top level evaluated drv')

  subparsers = parser.add_subparsers(title='subcommands')

  init_parser = subparsers.add_parser('init', help='prepare your working directory for other commands')
  init_parser.set_defaults(func=init)
  init_parser.add_argument('--migrate-state', action='store_true', help='reconfigure a backend, and attempt to migrate any existing state')
  init_parser.add_argument('--reconfigure', action='store_true', help='reconfigure a backend, ignoring any saved configuration')
  init_parser.add_argument('--upgrade', action='store_true', help='install the latest module and provider versions allowed within configured constraints, overriding the default behavior of selecting exactly the version recorded in the dependency lockfile.')

  repl_parser = subparsers.add_parser('repl', help='start an interactive REPL with the complete configuration')
  repl_parser.set_defaults(func=repl)
  repl_parser.add_argument('--debugger', action='store_true', help='start an interactive environment if evaluation fails')

  eval_parser = subparsers.add_parser('eval', help='evaluate an expression using the complete configuration')
  eval_parser.set_defaults(func=eval)
  eval_parser.add_argument('expr', type=str, nargs='+', help='the nix expression') # TODO: add an example, { resources, nodes, pkgs, lib, ... }:
  eval_parser.add_argument('--without-resources', action='store_true')
  group = eval_parser.add_mutually_exclusive_group()
  group.add_argument('--json', action='store_true')
  group.add_argument('--raw', action='store_true')

  plan_parser = subparsers.add_parser('plan', help='show changes required by the current configuration')
  plan_parser.set_defaults(func=plan)

  apply_parser = subparsers.add_parser('apply', parents=[confirm_parser], help='create or update all resources in the deployment')
  apply_parser.set_defaults(func=apply)

  build_parser = subparsers.add_parser('build', parents=[on_parser, with_drvs], help='build the system profiles')
  build_parser.set_defaults(func=build)

  push_parser = subparsers.add_parser('push', parents=[on_parser, with_drvs], help='copy the closures to remote nodes')
  push_parser.set_defaults(func=push)

  upload_keys_parser = subparsers.add_parser('upload-keys', parents=[on_parser], help='upload keys to remote hosts')
  upload_keys_parser.set_defaults(func=upload_keys)

  activate_parser = subparsers.add_parser('activate', parents=[on_parser, no_keys_parser, with_drvs], help='apply configurations on remote nodes')
  activate_parser.set_defaults(func=activate)
  group = activate_parser.add_mutually_exclusive_group()
  group.add_argument('--reboot', action='store_true', help='reboots nodes after activation and waits for them to come back up')
  group.add_argument('--dry-run', action='store_true', help='show what changes would be performed by the activation')

  deploy_parser = subparsers.add_parser('deploy', parents=[confirm_parser, on_parser, no_keys_parser], help='deploy the configuration')
  deploy_parser.set_defaults(func=deploy)
  deploy_parser.add_argument('--reboot', action='store_true', help='reboots nodes after activation and waits for them to come back up')

  destroy_parser = subparsers.add_parser('destroy', parents=[confirm_parser], help='destroy all resources in the deployment')
  destroy_parser.set_defaults(func=destroy)


  check_parser = subparsers.add_parser('check', help='attempt to connect to each node via SSH and print the results of the uptime command.')
  check_parser.set_defaults(func=check)

  ssh_parser = subparsers.add_parser('ssh', help='login on the specified machine via SSH')
  ssh_parser.set_defaults(func=ssh)
  ssh_parser.add_argument('node', type=str, help='identifier of the node')

  ssh_for_each_parser = subparsers.add_parser('ssh-for-each', parents=[on_parser], help='execute a command on each machine via SSH')
  ssh_for_each_parser.set_defaults(func=ssh_for_each)
  ssh_for_each_parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run')

  scp_parser = subparsers.add_parser('scp', help='copy files to or from the specified machine via scp')
  scp_parser.set_defaults(func=scp)
  scp_parser.add_argument('-r', action='store_true', help='recursively copy entire directories')
  scp_parser.add_argument('source', type=str, help='source file location')
  scp_parser.add_argument('target', type=str, help='destination file location')


  reboot_parser = subparsers.add_parser('reboot', parents=[on_parser], help='reboot all nodes in the deployment')
  reboot_parser.set_defaults(func=reboot)
  reboot_parser.add_argument('--no-wait', action='store_true', help='do not wait until the nodes are up again')

  args = parser.parse_args()

  # call the appropriate function based on the subcommand
  if hasattr(args, 'func'):
    try:
      await args.func(args)
    except subprocess.CalledProcessError as e:
      sys.exit(e.returncode)
    except CalledProcessError as e:
      console = Console(args.verbose)

      # https://stackoverflow.com/a/37059682
      value = codecs.escape_decode(e.stderr)[0].decode('utf-8')
      for line in value.splitlines():
        console.error(f'  stderr) {line}')
  else:
    # if no subcommand is provided, print help
    parser.print_help()

if __name__ == '__main__':
  run()

def run():
  asyncio.run(main())
