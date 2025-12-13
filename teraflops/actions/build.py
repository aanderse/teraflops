import asyncio
import codecs
import contextlib
import json
import sys

from teraflops import nodes, parsers, stages
from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.utils import generate_terraform_data_for_nix


async def run(args):
    errors = {}
    console = Console(args.verbose)

    async def pipeline(console, name, terraform_json, drv):
        try:
            if drv is None:
                drv = await stages.eval(console, name, terraform_json)
            await stages.build(console, name, drv)
        except CalledProcessError as e:
            errors[name] = e

    console.info('enumerating nodes...')
    selected, all = await nodes.filter(args)
    if len(all) == len(selected):
        console.info(f'selected all {len(selected)} nodes')
    else:
        console.info(f'selected {len(selected)} out of {len(all)} hosts')

    with console.refresh():
        context = contextlib.nullcontext() if args.with_drvs else generate_terraform_data_for_nix()
        async with context as terraform_json:
            if not args.with_drvs:
                console.info('terraform data gathered, ready to do work')

            if args.with_drvs:
                with open(args.with_drvs) as f:
                    drvs = json.load(f)

            async with asyncio.TaskGroup() as tg:
                for name in selected:
                    tg.create_task(pipeline(console, name, terraform_json, drvs[name] if args.with_drvs else None))

    for name, e in errors.items():
        console.error(f'failed to build to {name} - logs:')

        # https://stackoverflow.com/a/37059682
        value = codecs.escape_decode(e.stderr)[0].decode('utf-8')
        for line in value.splitlines():
            console.error(f'  stderr) {line}')

        console.error(f' failure) child process exited with error code: {e.returncode}')

    if len(errors) != 0:
        sys.exit(1)


def register_action(subparsers):
    parser = subparsers.add_parser(
        'build', parents=[parsers.on(), parsers.with_drvs()], help='build the system profiles'
    )
    parser.set_defaults(func=run)
