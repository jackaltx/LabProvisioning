from __future__ import absolute_import, division, print_function

__metaclass__ = type

import errno
import fcntl
import hashlib
import os
import pty
import shlex
import subprocess
import sys
import time

from ansible.release import __version__ as ansible_version
from functools import wraps
from ansible import constants as C
from ansible.errors import (
    AnsibleError,
    AnsibleConnectionFailure,
    AnsibleFileNotFound,
)
from ansible.compat import selectors
from ansible.module_utils.common.text.converters import to_bytes, to_native, to_text
from ansible.module_utils.parsing.convert_bool import BOOLEANS, boolean
from ansible.plugins.connection import ConnectionBase, BUFSIZE
from ansible.utils.path import unfrackpath, makedirs_safe
from ansible.errors import AnsibleOptionsError, AnsibleError, AnsibleFileNotFound
from ansible.module_utils.six import binary_type, text_type
from ansible.module_utils._text import to_bytes, to_native

DOCUMENTATION = """
    name: pct_ssh
    short_description: connect via ssh to proxmox host and execute pct commands
    description:
        - This connection plugin allows ansible to communicate to proxmox containers
          via ssh to the host and pct commands.
    author: Andreas Scherbaum
    options:
      pct_host:
        description: The container ID to connect to
        default: None
        vars:
          - name: pct_host
          - name: ansible_pct_host
        env:
          - name: ANSIBLE_PCT_HOST
        ini:
          - section: defaults
            key: pct_host
      host:
        description: Hostname/ip to connect to
        default: inventory_hostname
        vars:
          - name: inventory_hostname
          - name: ansible_host
          - name: ansible_ssh_host
      host_key_checking:
        description: Determines if ssh should check host keys
        type: boolean
        default: True
        vars:
          - name: ansible_host_key_checking
        env:
          - name: ANSIBLE_HOST_KEY_CHECKING
        ini:
          - section: defaults
            key: host_key_checking
      remote_user:
        description: User to login as
        default: root
        vars:
          - name: ansible_user
          - name: ansible_ssh_user
        env:
          - name: ANSIBLE_REMOTE_USER
        ini:
          - section: defaults
            key: remote_user
      private_key_file:
        description: Path to private key file
        vars:
          - name: ansible_private_key_file
          - name: ansible_ssh_private_key_file
        env:
          - name: ANSIBLE_PRIVATE_KEY_FILE
        ini:
          - section: defaults
            key: private_key_file
      port:
        description: SSH port number
        type: integer
        default: 22
        vars:
          - name: ansible_port
          - name: ansible_ssh_port
        env:
          - name: ANSIBLE_REMOTE_PORT
        ini:
          - section: defaults
            key: remote_port
      retries:
        description: Number of attempts to connect
        type: integer
        default: 3
        vars:
          - name: ansible_ssh_retries
        env:
          - name: ANSIBLE_SSH_RETRIES
        ini:
          - section: connection
            key: retries
          - section: ssh_connection
            key: retries
      remote_tmp:
        description: Temporary directory path on remote host
        default: /tmp
        vars:
          - name: ansible_remote_tmp
        env:
          - name: ANSIBLE_REMOTE_TMP
        ini:
          - section: defaults
            key: remote_tmp
"""

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()

class AnsibleControlPersistBrokenPipeError(AnsibleError):
    """ControlPersist broken pipe"""
    pass

class Connection(ConnectionBase):
    """ssh+pct connection to Proxmox containers"""

    transport = "pct_ssh"

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        super(Connection, self).__init__(play_context, new_stdin, *args, **kwargs)
        self.host = self._play_context.remote_addr
        self.port = self._play_context.port
        self.user = self._play_context.remote_user
        self._connected = False

    def _connect(self):
        """Connect to the Proxmox host"""
        super(Connection, self)._connect()
        
        container_id = self.get_option('pct_host')
        
        if not container_id:
            raise AnsibleError('pct_host (VMID) was not specified in inventory')
            
        self.container_name = str(container_id)
        
        if not self.container_name.isdigit():
            raise AnsibleError(f'Invalid container ID: {self.container_name}')
            
        display.vvv(f"PCT _connect::container={self.container_name} host={self.host}", host=self.host)
        
        # Create temp directory in container
        tmp_path = "/tmp/ansible-tmp"
        setup_cmd = f"sudo pct exec {self.container_name} -- mkdir -p {tmp_path}"
        ssh_cmd = self._build_command('ssh', setup_cmd)
        
        p = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        _, _ = p.communicate()
        
        self._connected = True
        return self

    def _build_command(self, binary, *other_args):
        """Build SSH command to connect to Proxmox host"""
        cmd = [binary]
        cmd.extend(['-o', 'ControlMaster=auto'])
        cmd.extend(['-o', 'ControlPersist=60s'])
        
        if not self.get_option('host_key_checking'):
            cmd.extend(['-o', 'StrictHostKeyChecking=no'])
            
        if self.port:
            cmd.extend(['-o', f'Port={self.port}'])
            
        key = self.get_option('private_key_file')
        if key:
            cmd.extend(['-o', f'IdentityFile={os.path.expanduser(key)}'])
            
        if self.user:
            cmd.extend(['-o', f'User={self.user}'])
            
        cmd.append(self.host)
        cmd.extend(other_args)
        return cmd

    def exec_command(self, cmd, in_data=None, sudoable=False):
        """Execute command in container through Proxmox host"""
        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)

        if not cmd:
            return (1, '', 'No command specified')

        if not self.container_name:
            raise AnsibleError("No container ID (pct_host) specified")

        display.vvv(f"(exec_command::Using container ID: {self.container_name}", host=self.host)
        
        # Use sudo with password if provided
        become_pass = self._play_context.become_pass
        if become_pass:
            sudo_cmd = f"echo {shlex.quote(become_pass)} | sudo -S pct exec {self.container_name} -- {cmd}"
        else:
            sudo_cmd = f"sudo pct exec {self.container_name} -- {cmd}"

        ssh_cmd = self._build_command('ssh', f'bash -c {shlex.quote(sudo_cmd)}')
        display.vvv(f"EXEC {' '.join(ssh_cmd)}", host=self.host)

        p = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        stdout, stderr = p.communicate()



        return (p.returncode, stdout, stderr)

    # def put_file(self, in_path, out_path):
    #     """Copy file to container through Proxmox host"""
    #     super(Connection, self).put_file(in_path, out_path)
        
    #     if not os.path.exists(to_bytes(in_path, errors="surrogate_or_strict")):
    #         raise AnsibleFileNotFound(f"file or module does not exist: {to_native(in_path)}")

    #     with open(in_path, "rb") as in_f:
    #         in_data = in_f.read()
    #         cmd = f"cat > {shlex.quote(out_path)}"
    #         pct_cmd = f'sudo pct exec {self.container_name} -- /bin/sh -c {shlex.quote(cmd)}'
    #         ssh_cmd = self._build_command('ssh', pct_cmd)
            
    #         display.vvv(f"PUT {in_path} TO {out_path}", host=self.host)
            
    #         p = subprocess.Popen(
    #             ssh_cmd,
    #             stdin=subprocess.PIPE,
    #             stdout=subprocess.PIPE,
    #             stderr=subprocess.PIPE
    #         )
            
    #         stdout, stderr = p.communicate(input=in_data)
    #         return (p.returncode, stdout, stderr)






    #######################################################################
    def put_file(self, in_path, out_path):
        """Copy file to container through Proxmox host using SSH and Cat"""
        super(Connection, self).put_file(in_path, out_path)
        if not os.path.exists(to_bytes(in_path, errors="surrogate_or_strict")):
            raise AnsibleFileNotFound(f"file or module does not exist: {to_native(in_path)}")

        with open(in_path, "rb") as in_f:
            in_data = in_f.read()

        become_pass = self._play_context.become_pass
        cmd = f"cat > {shlex.quote(out_path)}"
        pct_cmd = f'echo {become_pass} | sudo -S pct enter {self.container_name} -- /bin/sh -c {shlex.quote(cmd)}'
        ssh_cmd = self._build_command('ssh',pct_cmd) 


        display.vvv(f"PUT {in_path} TO {out_path}", host=self.host)
        display.vvv(f"cmd {cmd}", host=self.host)        
        display.vvv(f"pct_cmd {pct_cmd}", host=self.host)
        display.vvv(f"ssh_cmd {ssh_cmd}", host=self.host)

        try:
            p = subprocess.Popen(
                ssh_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = p.communicate(input=in_data.decode())
            display.vvv(f"SSH_STDOUT: {stdout}", host=self.host)
            display.vvv(f"SSH_STDERR: {stderr}", host=self.host)
        except subprocess.CalledProcessError as e:
            raise AnsibleError(f"Failed to copy {in_path} to {out_path}: {stderr.strip()}")
        except Exception as e:
            raise AnsibleError(f"Failed to copy {in_path} to {out_path}: {str(e)}")

        if p.returncode != 0:
            raise AnsibleError(f"Failed to copy {in_path} to {out_path}: {stderr.strip()}")

        display.vvv(f"File {out_path} successfully uploaded", host=self.host)






    # def put_file(self, in_path, out_path):
    #     """Copy file to container through Proxmox host using pct exec and Here-Document"""
    #     super(Connection, self).put_file(in_path, out_path)
    #     if not os.path.exists(to_bytes(in_path, errors="surrogate_or_strict")):
    #         raise AnsibleFileNotFound(f"file or module does not exist: {to_native(in_path)}")

    #     with open(in_path, "rb") as in_f:
    #         in_data = in_f.read()

    #     become_pass = self._play_context.become_pass
    #     pct_exec_cmd = [
    #         'ssh', self.host,
    #         'echo', become_pass, '|', 'sudo', '-S',
    #         'pct', 'exec', str(self.container_name), '--',
    #         '/bin/sh', '-c', f"cat {in_data} >  {shlex.quote(out_path)}"
    #     ]

    #     display.vvv(f"PUT {in_path} TO {out_path}", host=self.host)
    #     display.vvv(f"pct_exec_cmd {pct_exec_cmd}", host=self.host)

    #     try:
    #         subprocess.check_call(
    #             pct_exec_cmd,
    #             stdin=subprocess.PIPE,
    #             stderr=subprocess.STDOUT,
    #             universal_newlines=False
    #         )
    #         display.vvv(f"File {out_path} successfully uploaded", host=self.host)
    #     except subprocess.CalledProcessError as e:
    #         if 'sudo: a password is required' in e.output.decode():
    #             raise AnsibleError(f"Failed to copy {in_path} to {out_path}: Incorrect sudo password")
    #         else:
    #             raise AnsibleError(f"Failed to copy {in_path} to {out_path}: {e.output.decode().strip()}")
    #     except Exception as e:
    #         raise AnsibleError(f"Failed to copy {in_path} to {out_path}: {str(e)}")











    #######################################################################
    def fetch_file(self, in_path, out_path):
        """Fetch file from container through Proxmox host"""
        super(Connection, self).fetch_file(in_path, out_path)

        display.vvv(f"FETCH {in_path} TO {out_path}", host=self.host)

        cmd = f"cat {shlex.quote(in_path)}"
        pct_cmd = f'sudo pct exec {self.container_name} -- /bin/sh -c {shlex.quote(cmd)}'
        ssh_cmd = self._build_command('ssh', pct_cmd)
        
        p = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = p.communicate()
        
        if p.returncode != 0:
            raise AnsibleError(f"failed to fetch file from {in_path}:\n{stderr}")

        with open(out_path, "wb") as out_f:
            out_f.write(stdout)

        return (p.returncode, stdout, stderr)

    def close(self):
        """Close the connection"""
        self._connected = False

