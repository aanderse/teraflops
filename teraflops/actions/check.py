import asyncio

from teraflops import nodes, ssh
from teraflops.console import Console, Status


async def run(args):
    console = Console(verbosity=args.verbose)

    async def execute_on_node(ctx, name, node, command, private_key):
        # TODO: too verbose?
        msg = ctx.message(name, f'executing {command} on {node["targetHost"]}')

        process = await asyncio.create_subprocess_exec(
            *ssh.cmd(node, ['uptime'], private_key=private_key),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()

        if process.returncode != 0:
            msg.update('unavailable', status=Status.FAILURE)
        else:
            msg.update(stdout.decode().strip(), status=Status.SUCCESS)

    output_data = await nodes.get_teraflops_data()
    console.info('teraflops data gathered')

    with console.refresh() as ctx, ssh.get_private_key(output_data) as private_key:
        async with asyncio.TaskGroup() as tg:
            for name, deployment in output_data['nodes'].items():
                tg.create_task(execute_on_node(ctx, name, deployment, ['uptime'], private_key))


def register_action(subparsers):
    parser = subparsers.add_parser(
        'check', help='attempt to connect to each node via SSH and print the results of the uptime command.'
    )
    parser.set_defaults(func=run)
