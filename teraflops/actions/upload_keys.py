import asyncio
import codecs
import sys

from teraflops import nodes, parsers, ssh, stages
from teraflops.console import Console
from teraflops.error import CalledProcessError
from teraflops.utils import generate_terraform_data_for_nix


async def run(args):
    errors = {}
    console = Console(args.verbose)

    async def pipeline(console, name, node, terraform_json, private_key):
        try:
            await stages.upload_keys(console, name, node, terraform_json, private_key)
        except CalledProcessError as e:
            errors[name] = e

    console.info('enumerating nodes...')
    selected, all = await nodes.filter(args)
    if len(all) == len(selected):
        console.info(f'selected all {len(selected)} nodes')
    else:
        console.info(f'selected {len(selected)} out of {len(all)} hosts')

    output_data = await nodes.get_teraflops_data()
    console.info('teraflops data gathered')

    with console.refresh(), ssh.get_private_key(output_data) as private_key:
        async with generate_terraform_data_for_nix() as terraform_json:
            console.info('terraform data gathered, ready to do work')
            async with asyncio.TaskGroup() as tg:
                for name in selected:
                    tg.create_task(pipeline(console, name, output_data['nodes'][name], terraform_json, private_key))

    for name, e in errors.items():
        console.error(f'failed to upload keys to {name} - logs:')

        # https://stackoverflow.com/a/37059682
        value = codecs.escape_decode(e.stderr)[0].decode('utf-8')
        for line in value.splitlines():
            console.error(f'  stderr) {line}')

        console.error(f' failure) child process exited with error code: {e.returncode}')

    if len(errors) != 0:
        sys.exit(1)


def register_action(subparsers):
    parser = subparsers.add_parser('upload-keys', parents=[parsers.on()], help='upload keys to remote hosts')
    parser.set_defaults(func=run)
