import logging
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager

from rich.console import Console as RichConsole
from rich.markup import escape

from teraflops import ssh

log = logging.getLogger('teraflops.test')
console = RichConsole(highlight=False)


class RequestedAssertionFailed(AssertionError):
    """Raised when a test assertion (succeed, fail, etc.) does not hold."""
    pass


class Machine:
    """A remote NixOS machine — NixOS testing API over SSH."""

    def __init__(self, name, node, private_key=None):
        self.name = name
        self.node = node
        self.private_key = private_key
        # SSH ControlMaster for connection reuse — first call establishes a persistent
        # connection, subsequent calls multiplex over it with near-zero overhead
        self._control_path = tempfile.mktemp(prefix=f'teraflops-{name}-')

    def _log_msg(self, msg):
        log.info(f'{self.name}: {msg}')

    @contextmanager
    def _nested(self, msg):
        console.print(f'[bold green]{self.name}: {escape(msg)}[/]')
        start = time.monotonic()
        yield
        elapsed = time.monotonic() - start
        log.info(f'(finished: {msg}, in {elapsed:.2f} seconds)')

    def _ssh_cmd(self, command):
        extra_args = [
            '-o',
            f'ControlPath={self._control_path}',
            '-o',
            'ControlMaster=auto',
            '-o',
            'ControlPersist=60',
        ]
        return ssh.cmd(self.node, command, private_key=self.private_key, extra_args=extra_args)

    def _run(self, command, timeout=None, input=None):
        cmd = self._ssh_cmd(command)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)

    # ── Core execution (matches NixOS testing API) ─────────────────────

    def execute(self, command, timeout=900):
        """Run a shell command. Returns (status, stdout)."""
        console.print(f'[dim]{self.name}: running command: {escape(command)}[/]')
        result = self._run([command], timeout=timeout)
        console.print(f'[dim]{self.name}: exit status {result.returncode}[/]')
        return (result.returncode, result.stdout)

    def succeed(self, *commands):
        """Run commands, assert all exit 0. Returns combined stdout."""
        output = ''
        for command in commands:
            with self._nested(f'must succeed: {command}'):
                status, stdout = self.execute(command)
                if status != 0:
                    raise RequestedAssertionFailed(f'command `{command}` failed on {self.name} (exit code {status})')
                output += stdout
        return output

    def fail(self, *commands):
        """Run commands, assert all exit non-zero. Returns combined stdout."""
        output = ''
        for command in commands:
            with self._nested(f'must fail: {command}'):
                status, stdout = self.execute(command)
                if status == 0:
                    raise RequestedAssertionFailed(f'command `{command}` unexpectedly succeeded on {self.name}')
                output += stdout
        return output

    # ── Wait utilities ─────────────────────────────────────────────────

    def wait_until_succeeds(self, command, timeout=900):
        """Retry command until it succeeds."""
        with self._nested(f'waiting for success: {command}'):
            deadline = time.monotonic() + timeout
            while True:
                status, stdout = self.execute(command)
                if status == 0:
                    return stdout
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'command `{command}` did not succeed within {timeout}s on {self.name}')
                time.sleep(2)

    def wait_until_fails(self, command, timeout=900):
        """Retry command until it fails."""
        with self._nested(f'waiting for failure: {command}'):
            deadline = time.monotonic() + timeout
            while True:
                status, stdout = self.execute(command)
                if status != 0:
                    return stdout
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'command `{command}` did not fail within {timeout}s on {self.name}')
                time.sleep(2)

    def wait_for_unit(self, unit, timeout=900):
        """Wait for a systemd unit to be active."""
        with self._nested(f'waiting for unit {unit}'):
            deadline = time.monotonic() + timeout
            while True:
                status, stdout = self.execute(f"systemctl is-active '{unit}'")
                if status == 0:
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'unit {unit} did not become active within {timeout}s on {self.name}')
                time.sleep(2)

    def wait_for_open_port(self, port, addr='localhost', timeout=900):
        """Wait for a TCP port to accept connections."""
        with self._nested(f'waiting for open port {port}'):
            deadline = time.monotonic() + timeout
            while True:
                status, _ = self.execute(f"bash -c 'echo > /dev/tcp/{addr}/{port}'")
                if status == 0:
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'port {port} did not open within {timeout}s on {self.name}')
                time.sleep(2)

    def wait_for_closed_port(self, port, addr='localhost', timeout=900):
        """Wait for a TCP port to stop accepting connections."""
        with self._nested(f'waiting for closed port {port}'):
            deadline = time.monotonic() + timeout
            while True:
                status, _ = self.execute(f"bash -c 'echo > /dev/tcp/{addr}/{port}'")
                if status != 0:
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'port {port} did not close within {timeout}s on {self.name}')
                time.sleep(2)

    # ── Systemd helpers ────────────────────────────────────────────────

    def systemctl(self, command):
        """Run a systemctl command."""
        return self.succeed(f'systemctl {command}')

    def get_unit_info(self, unit):
        """Get systemd unit properties as a dict."""
        output = self.succeed(f"systemctl show '{unit}'")
        return dict(line.split('=', 1) for line in output.strip().splitlines() if '=' in line)

    # ── Lifecycle ──────────────────────────────────────────────────────

    def reboot(self):
        """Reboot and wait for the machine to come back."""
        with self._nested('reboot'):
            _, old_id = self.execute('cat /proc/sys/kernel/random/boot_id')
            self._run(['reboot'])
            time.sleep(5)
            deadline = time.monotonic() + 600
            while True:
                status, new_id = self.execute('cat /proc/sys/kernel/random/boot_id')
                if status == 0 and new_id.strip() != old_id.strip():
                    self._log_msg('back up after reboot')
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'reboot of {self.name} timed out')
                time.sleep(2)

    def shutdown(self):
        """Graceful shutdown."""
        self._log_msg('shutting down')
        self._run(['poweroff'])

    def start(self):
        """No-op stub for NixOS test API compatibility."""
        log.warning(f'{self.name}: start() is a no-op \u2014 teraflops delegates machine lifecycle to terraform')

    # ── File transfer ──────────────────────────────────────────────────

    def _scp_cmd(self):
        cmd = ['scp', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes']

        if self.private_key and self.node.get('provisionSSHKey'):
            cmd += ['-i', self.private_key]

        if self.node.get('targetPort'):
            cmd += ['-P', self.node['targetPort']]

        if os.environ.get('SSH_CONFIG_FILE'):
            cmd += ['-F', os.environ['SSH_CONFIG_FILE']]

        if self.node.get('sshOptions'):
            cmd += self.node['sshOptions']

        cmd += [
            '-o',
            f'ControlPath={self._control_path}',
            '-o',
            'ControlMaster=auto',
            '-o',
            'ControlPersist=60',
        ]

        return cmd

    def _remote_path(self, path):
        prefix = ''
        if self.node.get('targetUser'):
            prefix = f'{self.node["targetUser"]}@'
        host = self.node['targetHost']
        if ':' in host:
            host = f'[{host}]'
        return f'{prefix}{host}:{path}'

    def copy_from(self, remote_path, local_path):
        """SCP a file from the machine."""
        self._log_msg(f'scp: {remote_path} -> {local_path}')
        cmd = self._scp_cmd() + [self._remote_path(remote_path), local_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise OSError(f'failed to copy {remote_path} from {self.name}: {result.stderr}')

    def copy_to(self, local_path, remote_path):
        """SCP a file to the machine."""
        self._log_msg(f'scp: {local_path} -> {remote_path}')
        cmd = self._scp_cmd() + [local_path, self._remote_path(remote_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise OSError(f'failed to copy {local_path} to {self.name}: {result.stderr}')

    # ── Connection management ──────────────────────────────────────────

    def close(self):
        """Tear down the SSH ControlMaster socket."""
        subprocess.run(
            ['ssh', '-o', f'ControlPath={self._control_path}', '-O', 'exit', self.node['targetHost']],
            capture_output=True,
        )

    def __repr__(self):
        return f'<Machine {self.name!r}>'

    def __str__(self):
        return self.name
