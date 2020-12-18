#!/usr/bin/env python

import argparse
import json
import pika
import pika.exceptions
import sys

from .config import RABBITMQ_HOST


EXCHANGE_NAME = 'computing'


class ServerCommunication:
    def __enter__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST))
        self.channel = self.connection.channel()

        self.channel.basic_consume(
            queue='amq.rabbitmq.reply-to',
            on_message_callback=self.on_response,
            auto_ack=True)

        return self

    def on_response(self, ch, method, properties, body):
        self.responses.append(json.loads(body))

    def on_timeout(self):
        self.channel.stop_consuming()

    def send_msg(self, data, response_expected=False):
        self.responses = []

        reply_to = None
        if response_expected:
            reply_to = 'amq.rabbitmq.reply-to'

        self.channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=data['command'],
            properties=pika.BasicProperties(
                reply_to=reply_to,
                content_type='application/json',
            ),
            body=json.dumps(data).encode('utf-8'))

        if response_expected:
            self.connection.call_later(5, self.on_timeout)
            self.channel.start_consuming()

        return self.responses

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.close()


def main():
    parser = argparse.ArgumentParser(
        description='Manage aetherscale instances')
    subparsers = parser.add_subparsers(dest='subparser_name')

    create_vm_parser = subparsers.add_parser('create-vm')
    create_vm_parser.add_argument(
        '--image', help='Name of the image to create a VM from', required=True)
    create_vm_parser.add_argument(
        '--init-script', dest='init_script_path',
        help='Script to execute at first boot of VM', required=False)
    start_vm_parser = subparsers.add_parser('start-vm')
    start_vm_parser.add_argument(
        '--vm-id', dest='vm_id', help='ID of the VM to start', required=True)
    stop_vm_parser = subparsers.add_parser('stop-vm')
    stop_vm_parser.add_argument(
        '--vm-id', dest='vm_id', help='ID of the VM to stop', required=True)
    stop_vm_parser.add_argument(
        '--kill', dest='kill', action='store_true', default=False,
        help='Kill the VM immediately, no graceful shutdown')
    delete_vm_parser = subparsers.add_parser('delete-vm')
    delete_vm_parser.add_argument(
        '--vm-id', dest='vm_id', help='ID of the VM to delete', required=True)
    subparsers.add_parser('list-vms')

    args = parser.parse_args()

    if args.subparser_name == 'list-vms':
        response_expected = True
        data = {
            'command': 'list-vms',
        }
    elif args.subparser_name == 'create-vm':
        response_expected = True

        data = {
            'command': 'create-vm',
            'options': {
                'image': args.image,
            }
        }

        if args.init_script_path:
            with open(args.init_script_path, 'rt') as f:
                data['options']['init-script'] = f.read()
    elif args.subparser_name == 'stop-vm':
        response_expected = True
        data = {
            'command': args.subparser_name,
            'options': {
                'vm-id': args.vm_id,
                'kill': args.kill,
            }
        }
    elif args.subparser_name in ['start-vm', 'delete-vm']:
        response_expected = True
        data = {
            'command': args.subparser_name,
            'options': {
                'vm-id': args.vm_id,
            }
        }
    else:
        parser.print_usage()
        sys.exit(1)

    try:
        with ServerCommunication() as c:
            result = c.send_msg(data, response_expected)
            print(result)
    except pika.exceptions.AMQPConnectionError:
        print('Could not connect to AMQP broker. Is it running?',
              file=sys.stderr)
