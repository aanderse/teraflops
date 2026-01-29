import hashlib
import os
import shutil
import subprocess


class BinaryNotFoundError(Exception):
    pass


def terraform_config_file():
    """Return a deterministic terraform config filename based on the current working directory.

    Uses a hash of the cwd to avoid conflicts with user files while remaining
    deterministic for caching purposes.
    """
    cwd = os.getcwd()
    project_id = hashlib.sha256(cwd.encode()).hexdigest()[:12]
    return f'teraflops.{project_id}.tf.json'


def flake_ref():
    """Return a Nix expression that loads the current directory as a flake.

    Uses git+file:// when in a git repo to respect .gitignore and only
    include tracked files. Falls back to path: for non-git directories.
    """
    cwd = os.getcwd()

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
        )
        git_root = result.stdout.strip()
        subdir = os.path.relpath(cwd, git_root)

        if subdir == '.':
            return f'builtins.getFlake "git+file://{git_root}"'
        else:
            return f'builtins.getFlake "git+file://{git_root}?dir={subdir}"'
    except subprocess.CalledProcessError:
        return f'builtins.getFlake "path:{cwd}"'


def nix():
    for exe in ['nix', 'lix']:
        path = shutil.which(exe)
        if path:
            return path

    raise BinaryNotFoundError('could not find a suitable nix binary in $PATH')


def terraform():
    for exe in ['terraform', 'tofu']:
        path = shutil.which(exe)
        if path:
            return path

    raise BinaryNotFoundError('could not find a suitable terraform binary in $PATH')
