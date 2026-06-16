import asyncio
import json
from importlib.resources import files

from teraflops import utils
from teraflops.error import CalledProcessError
from teraflops.paths import flake_ref, nix, terraform

eval_path = files('teraflops.nix').joinpath('eval.nix')

async def get_teraflops_data():
    async with utils.generate_minimal_terraform_config():
        # query all outputs rather than the `teraflops` output by
        # name to avoid issues when state exists but is empty
        process = await asyncio.create_subprocess_exec(
            terraform(), 'output', '-json', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise CalledProcessError(process.returncode, stdout, stderr)

        outputs = json.loads(stdout)
        if 'teraflops' not in outputs:
            return {'nodes': {}}

        return outputs['teraflops']['value']

async def filter(args):
    all_node_names = await get_nodes_names()

    on = args.on.split(',') if args.on else None

    if on is None:
        return all_node_names, all_node_names

    tags_to_check = {value[1:] for value in on if value.startswith('@')}
    names_to_check = [value for value in on if not value.startswith('@')]

    if tags_to_check:
        try:
            # query tags from terraform state to avoid evaluation
            teraflops_data = await get_teraflops_data()
        except CalledProcessError:
            # without terraform state tags can't be resolved yet
            tag_map = {}
        else:
            tag_map = {name: set(node_data['tags']) for name, node_data in teraflops_data['nodes'].items()}

        return [
            name
            for name in all_node_names
            if (name in names_to_check) or (not tags_to_check.isdisjoint(tag_map.get(name, set())))
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
