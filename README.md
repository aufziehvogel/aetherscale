# aetherscale

aetherscale is small hobby project to create a hosting environment that can
be controlled via an HTTP API. I just want to have some fun and
dive deeper into Linux tooling (networking, virtualization and so on) and
into distributed applications. I do not think that this will become
production-ready at any point.

This is developed along with
[a blog tutorial series about scalable computing](https://blog.stefan-koch.name/2020/11/22/programming-cloud-hosting-python-rabbitmq-qemu)
which I am currently writing.

## Installation

You can install the package with:

```bash
git clone https://github.com/aufziehvogel/aetherscale
cd aetherscale
virtualenv venv && source venv/bin/activate
pip install -e .
```

Before you can start using the server you need to setup a TAP device to which
VDE networking can connect. This is needed so that the started VMs can
join the network. To be able to create a TAP device that is connected to your
real network, you might also have to setup a software bridge. Below are all
the steps, `$YOUR_USER` must be set to the user as which VDE and the
aetherscale server should run.

```
# Create a bridge connected to the real ethernet device (eth0)
ip link add br0 type bridge
ip link set br0 up

ip link set eth0 up
ip link set eth0 master br0

# Re-assign IP from eth0 to br0
ip addr flush dev eth0

# Assign IP to br0
ip addr add 192.168.0.10/24 brd + dev br0
ip route add default via 192.168.0.1 dev br0

# Setup a TAP device to which VDE can connect
ip tuntap add dev tap-vde mode tap user $YOUR_USER
ip link set dev tap-vde up
ip link set tap-vde master br0
```

## Usage

The server can be started with:

```bash
aetherscale
```

For example, to list all running VMs run the following client command:

```bash
aetherscale-cli list-vms
```

## Run Tests

You can run tests with `tox`:

```bash
tox
```


## Overview

Components which I think would be interesting to develop are:

- Firewall (probably nftables, so that I can learn nftables)
- Virtual Private Networks (probably tinc)
- Virtual Servers (probably qemu)
  - IPv6-only intranet to learn IPv6

## Architecture

My idea is that all requests to the system go through a central message
broker. Handlers will then pick up these tasks and perform the work.

Each request can have the name of a unique channel for responses. The sender
of a message can open a channel with this name on the broker and will receive
responses. This is useful if you have to wait until another component has
performed their work.

### Messages

Create a new machine:

```json
{
   "component": "computing",
   "task": "create-vm",
   "response-channel": "unique-channel-123456789",
   "options": {
      "image": "my-image",
      "virtual-network": "my-virtual-subnet",
      "public-ip": true,
   }
}
```

### Computing

Stuff I use for computing (and thus have learnt something about so far):

- Qemu
- software bridging with `ip` (for public and private IPs)
  - VDE could also be relevant, but currently out of scope
- layer-2 VPN with tinc
- `libguestfs` for analyzing and changing images


## Contribution

If you want to contribute you can:

- create some steampunk artwork for this project :)
- think about what else could be interesting to implement (especially if
  it runs as a daemon it should be based on well-established Linux technology
  that runs without babysitting it all day long)
- create a routine for simple setup of the root installation steps
