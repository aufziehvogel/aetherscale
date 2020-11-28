import json
import os
from pathlib import Path
import pika
import psutil
import random
import string
import subprocess
import sys
from typing import List, Optional

from . import interfaces


QUEUE_NAME = 'vm-queue'
BASE_IMAGE_FOLDER = Path('base_images')
USER_IMAGE_FOLDER = Path('user_images')

run_qemu_username = os.getenv('RUN_QEMU_AS')

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

channel.queue_declare(queue=QUEUE_NAME)


class QemuException(Exception):
    pass


def create_user_image(vm_id: str, image_name: str) -> Path:
    base_image = BASE_IMAGE_FOLDER / f'{image_name}.qcow2'
    if not base_image.is_file():
        raise IOError(f'Image "{image_name}" does not exist')

    user_image = USER_IMAGE_FOLDER / f'{vm_id}.qcow2'

    create_img_result = subprocess.run([
        'qemu-img', 'create', '-f', 'qcow2',
        '-b', str(base_image.absolute()), '-F', 'qcow2', str(user_image)])
    if create_img_result.returncode != 0:
        raise QemuException(f'Could not create image for VM "{vm_id}"')

    return user_image


def list_vms() -> List[str]:
    vms = []

    for proc in psutil.process_iter(['pid', 'name']):
        if proc.name().startswith('vm-'):
            vms.append(proc.name())

    return vms


def get_process_for_vm(vm_id: str) -> Optional[psutil.Process]:
    for proc in psutil.process_iter(['name']):
        if proc.name() == vm_id:
            return proc

    return None


def callback(ch, method, properties, body):
    message = body.decode('utf-8')
    print('Received message: ' + message)

    data = json.loads(message)
    response = None

    if 'command' not in data:
        return
    elif data['command'] == 'list-vms':
        response = list_vms()
    elif data['command'] == 'stop-vm':
        try:
            vm_id = data['options']['vm-id']
        except KeyError:
            print('VM ID not specified', file=sys.stderr)
            return

        process = get_process_for_vm(vm_id)
        if process:
            process.kill()
            response = {
                'status': 'killed',
                'vm-id': vm_id,
            }
        else:
            response = {
                'status': 'error',
                'reason': f'VM "{vm_id}" does not exist',
            }
    elif data['command'] == 'start-vm':
        vm_id = ''.join(
            random.choice(string.ascii_lowercase) for i in range(8))
        print(f'Starting VM "{vm_id}"')

        try:
            image_name = os.path.basename(data['options']['image'])
        except KeyError:
            print('Image not specified', file=sys.stderr)
            return

        try:
            user_image = create_user_image(vm_id, image_name)
        except (OSError, QemuException) as e:
            print(str(e), file=sys.stderr)
            return

        tap_device = f'vm-{vm_id}'
        if not interfaces.create_tap_device(
                tap_device, 'br0', run_qemu_username):
            print(f'Could not create tap device for VM "{vm_id}"',
                  file=sys.stderr)
            return

        mac_addr = interfaces.create_mac_address()
        print(f'Assigning MAC address "{mac_addr}" to VM "{vm_id}"')

        p = subprocess.Popen([
            'qemu-system-x86_64', '-m', '4096', '-hda', str(user_image),
            '-device', f'virtio-net-pci,netdev=pubnet,mac={mac_addr}',
            '-netdev', f'tap,id=pubnet,ifname={tap_device},script=no,downscript=no',
            '-name', f'qemu-vm-{vm_id},process=vm-{vm_id}',
        ])
        print(f'Started VM "{vm_id}" as process ID {p.pid}')

    ch.basic_ack(delivery_tag=method.delivery_tag)

    if response is not None and properties.reply_to:
        ch.basic_publish(
            exchange='',
            routing_key=properties.reply_to,
            properties=pika.BasicProperties(
                correlation_id=properties.correlation_id
            ),
            body=json.dumps(response))


def run():
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

    if not interfaces.check_device_existence('br0'):
        interfaces.init_bridge(
            'br0', 'enp0s25', '192.168.2.10/24', '192.168.2.1')

    channel.start_consuming()
