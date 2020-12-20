import logging
import random
import re
import subprocess
from typing import Optional

from aetherscale import execution


def create_mac_address() -> str:
    # Set second least significant bit of leftmost pair to 1 (local)
    # Set least significant bit of leftmost pair to 0 (unicast)
    mac_bits = (random.getrandbits(48) | 0x020000000000) & 0xfeffffffffff
    mac_str = '{:012x}'.format(mac_bits)
    return ':'.join([
        mac_str[:2], mac_str[2:4], mac_str[4:6],
        mac_str[6:8], mac_str[8:10], mac_str[10:],
    ])


class NetworkingException(Exception):
    pass


class Iproute2Network:
    @staticmethod
    def bridged_network(
            bridge_device: str, phys_device: str,
            ip: Optional[str] = None, gateway: Optional[str] = None,
            flush_ip_device: bool = True) -> bool:
        Iproute2Network.validate_device_name(bridge_device)
        Iproute2Network.validate_device_name(phys_device)
        if ip:
            Iproute2Network.validate_ip_address(ip)
        if gateway:
            Iproute2Network.validate_ip_address(gateway)

        Iproute2Network._create_bridge(bridge_device)

        commands = [
            ['sudo', 'ip', 'link', 'set', phys_device, 'up'],
            ['sudo', 'ip', 'link', 'set', phys_device, 'master', bridge_device],
            ['sudo', 'ip', 'addr', 'flush', 'dev', phys_device],
        ]

        if ip:
            if flush_ip_device:
                commands.append(
                    ['sudo', 'ip', 'addr', 'flush', 'dev', bridge_device])
            commands.append(
                ['sudo', 'ip', 'addr', 'add', ip, 'dev', bridge_device])
        if gateway:
            commands.append(
                ['sudo', 'ip', 'route', 'add', 'default',
                 'via', gateway, 'dev', bridge_device])

        return execution.run_command_chain(commands)

    @staticmethod
    def tap_device(
            tap_device_name: str, user: str,
            bridge_device: Optional[str] = None):
        Iproute2Network.validate_device_name(tap_device_name)
        if bridge_device:
            Iproute2Network.validate_device_name(bridge_device)

        if Iproute2Network.check_device_existence(tap_device_name):
            logging.debug(
                f'Device {tap_device_name} already exists, will not re-create')
            return True
        else:
            logging.debug(f'Creating TAP device {tap_device_name}')

            commands = [
                ['sudo', 'ip', 'tuntap', 'add', 'dev', tap_device_name,
                 'mode', 'tap', 'user', user],
                ['sudo', 'ip', 'link', 'set', 'dev', tap_device_name, 'up'],
            ]

            if bridge_device:
                commands.append([
                    'sudo', 'ip', 'link', 'set', tap_device_name,
                    'master', bridge_device,
                ])

            creation_ok = execution.run_command_chain(commands)
            return creation_ok

    @staticmethod
    def _create_bridge(bridge_device: str):
        Iproute2Network.validate_device_name(bridge_device)

        if Iproute2Network.check_device_existence(bridge_device):
            logging.debug(
                f'Device {bridge_device} already exists, will not re-create')
            return True
        else:
            logging.debug(f'Creating bridge device {bridge_device}')

            return execution.run_command_chain([
                ['sudo', 'ip', 'link', 'add', bridge_device, 'type', 'bridge'],
                ['sudo', 'ip', 'link', 'set', bridge_device, 'up'],
            ])

    @staticmethod
    def check_device_existence(device: str) -> bool:
        Iproute2Network.validate_device_name(device)

        # if ip link show dev [devicename] does not find [devicename], it will
        # write a message to stderr, but none to stdout
        result = subprocess.run(
            ['ip', 'link', 'show', 'dev', device], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)

        if result.stdout:
            return True
        else:
            return False

    @staticmethod
    def validate_device_name(name: str):
        if len(name) == 0:
            raise NetworkingException('Zero-length device name not allowed')
        elif len(name) > 15:
            raise NetworkingException('Device name must be max. 15 characters')
        elif not re.match('^[a-z0-9-]+$', name):
            raise NetworkingException(
                f'Invalid name for network device provided ("{name}")')

    @staticmethod
    def validate_ip_address(ip_addr: str):
        if not re.match(r'^[0-9.:a-f]+(/\d+)?$', ip_addr):
            raise NetworkingException(
                f'Invalid IP address provided ({ip_addr})')
