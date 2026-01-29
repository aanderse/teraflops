import argparse
import asyncio

from teraflops import nodes, parsers, ssh
from teraflops.console import Console, Status


async def run(args):
    console = Console(verbosity=args.verbose)

    async def execute_on_node(ctx, name, node, command, private_key):
        msg = ctx.message(name)

        if args.verbose >= 1:
            msg.update('executing remote command')

        process = await asyncio.create_subprocess_exec(
            *ssh.cmd(node, command, private_key=private_key),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            msg.update(f'failed: {stderr.decode().strip()}', status=Status.FAILURE)
        else:
            msg.update(stdout.decode().strip(), status=Status.SUCCESS)

    output_data = await nodes.get_teraflops_data()

    console.info('enumerating nodes...')
    selected, all = await nodes.filter(args)
    if len(all) == len(selected):
        console.info(f'selected all {len(selected)} nodes')
    else:
        console.info(f'selected {len(selected)} out of {len(all)} hosts')

    with console.refresh() as ctx, ssh.get_private_key(output_data) as private_key:
        async with asyncio.TaskGroup() as tg:
            for name in selected:
                tg.create_task(execute_on_node(ctx, name, output_data['nodes'][name], args.command, private_key))


def register_action(subparsers):
    parser = subparsers.add_parser(
        'ssh-for-each', parents=[parsers.on()], help='execute a command on each machine via SSH'
    )
    parser.set_defaults(func=run)
    parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run')
