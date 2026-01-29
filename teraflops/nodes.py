import asyncio
import json
from importlib.resources import files

from teraflops import utils
from teraflops.error import CalledProcessError
from teraflops.paths import flake_ref, nix, terraform

eval_path = files('teraflops.nix').joinpath('eval.nix')


# the only thing this is (currently?) used for is get_teraflops_data()['nodes']
async def get_teraflops_data():
    async with utils.generate_minimal_terraform_config():
        process = await asyncio.create_subprocess_exec(
            terraform(), 'output', '-json', 'teraflops', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, stdout, stderr)

        return json.loads(stdout)


# on `terraform apply` various pieces of information from each nodes `config.deployment.*` configuration is stored in
# terraform state - this information provides an extremely quick lookup which entirely bypasses nix evaluation
async def query_cache(name):
    async with utils.generate_minimal_terraform_config():
        process = await asyncio.create_subprocess_exec(
            terraform(), 'output', '-json', 'teraflops', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, stdout, stderr)

        # FIXME: guard against nodes which aren't there
        return json.loads(stdout)['nodes'][name]


############################################################


async def filter(args):
    all_node_names = await get_nodes_names()

    # TODO: is querying tags from nix significantly slower than querying from terraform??
    async def get_node_tags(name):
        cmd_args = [
            '--extra-experimental-features',
            'flakes nix-command',
            'eval',
            '--impure',
            '--json',
            '--expr',
            f'''
              (import {eval_path} {{
                flake = {flake_ref()};
              }}).nodes."{name}".config.deployment.tags
            ''',
        ]

        process = await asyncio.create_subprocess_exec(
            nix(), *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, stdout, stderr)

        return name, json.loads(stdout)

    #########################################

    on = args.on.split(',') if args.on else None

    if on is None:
        return all_node_names, all_node_names

    tags_to_check = {value[1:] for value in on if value.startswith('@')}
    names_to_check = [value for value in on if not value.startswith('@')]

    if tags_to_check:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(get_node_tags(name)) for name in all_node_names]

        tag_map = dict(task.result() for task in tasks)

        return [
            name for name in all_node_names if (name in names_to_check) or (not tags_to_check.isdisjoint(tag_map[name]))
        ], all_node_names

    return [name for name in all_node_names if name in names_to_check], all_node_names


async def get_nodes_names():
    cmd = [
        nix(),
        '--extra-experimental-features',
        'flakes nix-command',
        'eval',
        '--impure',
        '--json',
        '--expr',
        f'builtins.attrNames (import {eval_path} {{ flake = {flake_ref()}; }}).nodes',
    ]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise CalledProcessError(process.returncode, stdout, stderr)

    return json.loads(stdout)
