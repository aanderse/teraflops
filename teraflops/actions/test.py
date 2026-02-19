import asyncio
import json
import logging
import os
import sys
import time
import traceback
from contextlib import contextmanager
from importlib.resources import files

from rich.markup import escape

from teraflops import nodes, ssh
from teraflops.paths import flake_ref, nix
from teraflops.testing.machine import Machine, RequestedAssertionFailed, console

eval_path = files('teraflops.nix').joinpath('eval.nix')

log = logging.getLogger('teraflops.test')


@contextmanager
def subtest(name):
    console.print(f'[bold green]subtest: {escape(name)}[/]')
    start = time.monotonic()
    try:
        yield
    except Exception as e:
        console.print(f'[red]!!! Test "{escape(name)}" failed with error: "{escape(str(e))}"[/]')
        raise
    else:
        elapsed = time.monotonic() - start
        log.info(f'(finished: subtest: {name}, in {elapsed:.2f} seconds)')


def start_all():
    log.warning('start_all() is a no-op \u2014 teraflops delegates machine lifecycle to terraform')


def _log_test_failure(test_script, script_name):
    """Log a test assertion failure with a filtered traceback showing only test script frames."""
    exc_type, exc, tb = sys.exc_info()

    # filter traceback to only frames from the test script (not framework internals)
    filtered = [
        frame
        for frame in traceback.extract_tb(tb)
        if frame.filename == script_name
    ]

    console.print()
    console.print('[red]!!! Traceback (most recent call last):[/]')

    code = test_script.splitlines()
    for frame in filtered:
        console.print(f'[red]!!!   File "{escape(script_name)}", line {frame.lineno}, in {escape(frame.name)}[/]')
        if frame.lineno and frame.lineno <= len(code):
            console.print(f'[red]!!!     {escape(code[frame.lineno - 1].strip())}[/]')

    console.print(f'[red]!!! {escape(str(exc))}[/]')


async def _eval_nix_test_script(nix_file=None):
    """Evaluate a testScript from nix. If nix_file is given, import and evaluate that file;
    otherwise evaluate the testScript from the flake configuration."""
    if nix_file:
        abs_path = os.path.abspath(nix_file)
        log.info(f'evaluating test script from {nix_file}...')
        expr = f'(import {eval_path} {{ flake = {flake_ref()}; }}).evalFn (import {abs_path})'
    else:
        log.info('evaluating testScript...')
        expr = f'(import {eval_path} {{ flake = {flake_ref()}; }}).testScript'

    cmd = [
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'eval',
        '--impure',
        '--json',
        '--expr',
        expr,
    ]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        log.error(f'failed to evaluate testScript:\n{stderr.decode().strip()}')
        sys.exit(1)

    test_script = json.loads(stdout)

    if test_script is None:
        log.error('no testScript defined in configuration')
        sys.exit(1)

    if not isinstance(test_script, str):
        log.error(f'testScript must be a string, got {type(test_script).__name__}')
        sys.exit(1)

    return test_script


async def run(args):
    # set up NixOS-test-style logging: plain messages to stdout, no decoration
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(handler)
    log.propagate = False

    # 1. load test script
    if args.file and args.file.endswith('.nix'):
        test_script = await _eval_nix_test_script(args.file)
    elif args.file and args.file.endswith('.py'):
        log.info(f'loading test script from {args.file}...')
        try:
            with open(args.file) as f:
                test_script = f.read()
        except FileNotFoundError:
            log.error(f'test script not found: {args.file}')
            sys.exit(1)
    elif args.file:
        log.error(f'unsupported file extension: {args.file}')
        log.error('')
        log.error('expected a .py or .nix file:')
        log.error('')
        log.error('  .py  Python test script executed directly. Machines are')
        log.error('       available as globals by name (e.g. myserver.succeed(...)).')
        log.error('')
        log.error('  .nix Nix expression that returns a Python test script string.')
        log.error('       Can be a bare string or a function that receives')
        log.error('       { nodes, pkgs, lib, resources, outputs } and returns a string.')
        sys.exit(1)
    else:
        test_script = await _eval_nix_test_script()

    # 2. get node data from terraform state
    log.info('enumerating nodes...')
    output_data = await nodes.get_teraflops_data()

    # 3. create machines and run test script
    machines = {}
    with ssh.get_private_key(output_data) as private_key:
        try:
            for name, node in output_data['nodes'].items():
                machines[name] = Machine(name, node, private_key)

            globals_dict = dict(machines)
            globals_dict['subtest'] = subtest
            globals_dict['start_all'] = start_all
            globals_dict['log'] = log

            script_name = args.file if args.file else '<testScript>'

            log.info(f'running testScript against {len(machines)} node(s)...\n')

            start = time.monotonic()
            exec(compile(test_script, script_name, 'exec'), globals_dict)
            elapsed = time.monotonic() - start

            log.info(f'\ntest script finished in {elapsed:.2f}s')
        except RequestedAssertionFailed:
            _log_test_failure(test_script, script_name)
            sys.exit(1)
        except Exception as e:
            log.error(f'\ntest script failed: {e}')
            sys.exit(1)
        finally:
            for m in machines.values():
                m.close()


def register_action(subparsers):
    parser = subparsers.add_parser(
        'test',
        help='run the testScript against deployed machines',
    )
    parser.add_argument(
        '-f', '--file',
        help='path to a test script file (.py or .nix) instead of using the inline testScript',
    )
    parser.set_defaults(func=run)
