import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from typing import Optional

from aetherscale.services import ServiceManager


class VpnException(Exception):
    pass


class TincVirtualNetwork(object):
    def __init__(
            self, netname: str, config_folder: Path,
            service_manager: ServiceManager):
        if not self._validate_netname(netname):
            raise ValueError(
                f'Invalid name for network provided ("{netname}")')

        self.netname = netname
        self.config_base_folder = config_folder
        self.service_manager = service_manager
        # TODO: To support multi VPN each VPN has to use another port
        self.port = 20000

        self.pidfile = Path(tempfile.gettempdir()) / f'tincd-{self.netname}.run'

    def network_exists(self) -> bool:
        return self._net_config_folder().is_dir()

    @property
    def interface_name(self):
        return f'tinc-{self.netname}'

    @property
    def bridge_interface_name(self):
        return f'tincbr-{self.netname}'

    def create_config(self, hostname: str):
        if not re.match('^[a-z0-9]+$', hostname):
            raise ValueError(f'Invalid hostname provided ("{hostname}")')

        config_dir = self._net_config_folder()
        config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_dir / 'tinc.conf', 'w') as f:
            lines = [
                f'Name = {hostname}\n',
                'Mode = switch\n',
                f'Interface = {self.interface_name}\n',
                f'Port = {self.port}\n',
            ]
            f.writelines(lines)

        self._create_host(hostname, public_ip=None, pubkey=None)

    def add_peer(self, hostname: str, public_ip: str, pubkey: str):
        self._create_host(hostname, public_ip, pubkey)

        with open(self._net_config_folder() / 'tinc.conf', 'a') as f:
            f.write(f'ConnectTo = {hostname}')

    def _create_host(
            self, hostname: str, public_ip: Optional[str],
            pubkey: Optional[str]):
        hosts_dir = self._net_config_folder() / 'hosts'
        os.makedirs(hosts_dir, exist_ok=True)

        with open(hosts_dir / hostname, 'w') as f:
            if public_ip:
                f.write(f'Address = {public_ip}\n')

            if pubkey:
                f.write('\n')
                f.write(pubkey)

    def gen_keypair(self):
        logging.debug('Generating key pair for tinc')
        subprocess.run(
            ['tincd', '-K', '-c', self._net_config_folder()],
            stdin=subprocess.DEVNULL)
        logging.debug('Finished generating key pair')

    def _validate_netname(self, netname: str):
        if not re.match('^[a-z0-9]+$', netname):
            return False
        if len(netname) > 8:
            return False

        return True

    def _net_config_folder(self) -> Path:
        return self.config_base_folder / self.netname

    def _service_name(self) -> str:
        return f'aetherscale-tincd-{self.netname}.service'

    def start_daemon(self):
        net_dir_quoted = shlex.quote(str(self._net_config_folder()))
        pidfile_quoted = shlex.quote(str(self.pidfile))

        service_name = self._service_name()
        with tempfile.NamedTemporaryFile('wt') as f:
            f.write('[Unit]\n')
            f.write(f'Description=aetherscale {self.netname} VPN with tincd\n')
            f.write('\n')
            f.write('[Service]\n')
            f.write(
                f'ExecStart=tincd -D -c {net_dir_quoted} '
                f'--pidfile {pidfile_quoted}\n')
            f.write('\n')
            f.write('[Install]\n')
            f.write('WantedBy=default.target\n')

            f.flush()

            logging.debug(f'Installing tinc VPN service "{service_name}"')
            self.service_manager.install_service(Path(f.name), service_name)

        self.service_manager.enable_service(service_name)
        success = self.service_manager.start_service(service_name)
        if not success:
            raise VpnException(f'Could not establish VPN "{self.netname}"')

    def teardown_tinc_config(self):
        self.service_manager.uninstall_service(self._service_name())
        shutil.rmtree(self._net_config_folder())
