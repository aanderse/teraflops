import contextlib
import os
import tempfile


def opts(node, private_key=None):
    opts = ['-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes', '-T']

    if private_key and node.get('provisionSSHKey'):
        opts += ['-i', private_key]

    if os.environ.get('SSH_CONFIG_FILE'):
        opts += ['-F', os.environ['SSH_CONFIG_FILE']]

    if node.get('targetPort'):
        opts += ['-p', node['targetPort']]

    if node.get('targetUser'):
        opts += ['-l', node.get('targetUser')]

    if node.get('sshOptions'):
        opts += node['sshOptions']

    return opts


def cmd(node, command=None, private_key=None, extra_args=None):
    cmd = [
        'ssh',
        '-o',
        'StrictHostKeyChecking=accept-new',
        '-o',
        'BatchMode=yes',
    ]

    if command:
        cmd += ['-T']

    if private_key and node.get('provisionSSHKey'):
        cmd += ['-i', private_key]

    if extra_args:
        cmd += extra_args

    if os.environ.get('SSH_CONFIG_FILE'):
        cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

    if node.get('targetPort'):
        cmd += ['-p', node['targetPort']]

    if node.get('targetUser'):
        cmd += ['-l', node.get('targetUser')]

    if node.get('sshOptions'):
        cmd += node['sshOptions']

    cmd += [node['targetHost']]

    if command:
        cmd += command

    return cmd


@contextlib.contextmanager
def get_private_key(output_data, *nodes):
    might_need_ssh_key = nodes and any(node['provisionSSHKey'] for node in nodes) or not nodes
    have_ssh_key = output_data['privateKey']

    if might_need_ssh_key and have_ssh_key:
        with tempfile.TemporaryDirectory(prefix='teraflops', delete=True) as tempdir:
            private_key_path = os.path.join(tempdir, 'id_ed25519')

            with open(os.open(private_key_path, os.O_CREAT | os.O_WRONLY, 0o600), 'w') as f:
                f.write(output_data['privateKey'])
                f.close()

            yield private_key_path
    else:
        with contextlib.nullcontext():
            yield None
