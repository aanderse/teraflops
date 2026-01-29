from teraflops.utils import generate_full_terraform_config


async def run(args):
    async with generate_full_terraform_config() as config_file:
        with open(config_file) as f:
            print(f.read())


def register_action(subparsers):
    parser = subparsers.add_parser('dump', help='dump the generated terraform configuration as json')
    parser.set_defaults(func=run)
