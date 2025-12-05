#!/usr/bin/env python3

import argparse
import asyncio
import codecs
import importlib
import os
import subprocess
import sys

from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.paths import BinaryNotFoundError

async def main():

  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbose', action='store_true')

  subparsers = parser.add_subparsers(title='subcommands')

  # dynamically register all actions
  actions_dir = os.path.join(os.path.dirname(__file__), "actions")
  if os.path.isdir(actions_dir):
    for filename in os.listdir(actions_dir):
      if filename.endswith(".py") and filename != "__init__.py":
        module_name = filename[:-3]  # Remove .py extension

        module = importlib.import_module(f'teraflops.actions.{module_name}')
        module.register_action(subparsers)


  args = parser.parse_args()

  # call the appropriate function based on the subcommand
  if hasattr(args, 'func'):
    try:
      await args.func(args)
    except BinaryNotFoundError as e:
      print(f'{parser.prog}: error: {e}')
      sys.exit(1)
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

def run():
  asyncio.run(main())

if __name__ == '__main__':
  run()
