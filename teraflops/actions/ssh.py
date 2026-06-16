import argparse
import difflib
import subprocess

from teraflops import nodes, ssh


async def run(args):
    output_data = await nodes.get_teraflops_data()
    available = output_data['nodes'].keys()

    if args.node in available:
        node = output_data['nodes'][args.node]

        extra_args = ['-' + 'v' * args.verbose] if args.verbose else None

        with ssh.get_private_key(output_data, node) as private_key:
            subprocess.run(ssh.cmd(node, args.command or None, private_key=private_key, extra_args=extra_args))
    else:
        matches = difflib.get_close_matches(args.node, available, n=5, cutoff=0.6)

        if matches:
            print(f'node `{args.node}` does not exist - did you mean one of: {", ".join(matches)}?')
        else:
            print(f'node `{args.node}` does not exist')


def register_action(subparsers):
    parser = subparsers.add_parser('ssh', help='login on the specified machine via SSH')
    parser.set_defaults(func=run)
    parser.add_argument('-v', '--verbose', action='count', default=0, help='increase verbosity (passed through to ssh, e.g. -v, -vv, -vvv)')
    parser.add_argument('node', type=str, help='identifier of the node')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run')
