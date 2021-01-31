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

I recommend that you install the package in a virtual environment for
easy removal and to avoid conficts with system-wide stuff:

```bash
git clone https://github.com/aufziehvogel/aetherscale
cd aetherscale
virtualenv venv && source venv/bin/activate
pip install .
```

### Operating System Changes

I am trying to design aetherscale to run without root permissions for
as much as possible.
For some actions more permissions than a standard user usually has are
needed, though. This section will guide you through all of the changes
required to allow aetherscale itself to run as a standard user.

#### Networking

aetherscale has to adjust your networking in order to expose the VMs to the
network. I decided to setup a bridge network for the VMs to join with
`iproute2`.

Bridge networks are used in two different situations:

1. When exposing the VM to the public internet
2. When establishing a VPN network between multiple VMs

In both cases we use the `iproute2` (`ip`) utility. To allow aetherscale to
run as a non-root user while still having access to networking changes, I
decided to use `sudo` and allow rootless access to `ip`.

For VPN there currently is one more change needed (but this is only
temporary). To auto-configure IPv6 addresses of VPNs inside
the guest VM we use IPv6 Router Advertisement messages. We run a `radvd`
server that sends out the prefixes for IPv6 addresses. `radvd` also requires
root permissions (to be exact it requires `CAP_NET_RAW` permissions).

To allow these calls you have to enable passwordless sudo permissions with
the following entry in `visudo`:

```
youruser ALL=(ALL) NOPASSWD: /usr/bin/ip, /usr/bin/radvd
```

Having `radvd` on the host machine is only a temporary solution. In a real
setup, the VPN has to manage the internal IP addresses itself. We will
probably provide an init-script template for a machine that does this.

Requiring `sudo` is not a perfect solution but Linux capabilities inheritance to
subprocesses seems quite complicated, and without inheritance we'd have to grant
`CAP_NET_ADMIN` to both `ip` and `tincd`. This might be undesired, because
then any user can change network devices. Another option could be to
assign `CAP_NET_ADMIN` to the user running aetherscale, but this seems to
[require changes to pam](https://unix.stackexchange.com/questions/454708/how-do-you-add-cap-sys-admin-permissions-to-user-in-centos-7)
and still seems to require inheritable capabilities to be set on each
binary that is to be executed.
While this in my opinion would be a reasonable choice for a production
program, it feels too heavy for a proof-of-concept tool.

## Getting Started

Each VM is booted from a base image, which has to be created in advance.
This means that at first you have to create a base image. Download an
installation ISO for your favourite Linux distribution and install it to a
qcow2 file with the following commands, following the installation instruction
inside the started QEMU VM.

```bash
BASE_IMAGE=base-image-name.qcow2
ISO=your-distribution.iso
qemu-img create -f qcow2 $BASE_IMAGE 20G
qemu-system-x86_64 -cpu host -accel kvm -m 4096 -hda $BASE_IMAGE -cdrom $ISO
```

The qcow2 is your base image. It must be located inside the
`$BASE_IMAGE_FOLDER` directory. This is a configurable environment variable.

aetherscale expects a bridge network `br0` on the physical ethernet which can
be used to attach additional TAP interfaces for VMs. If this interface does not
exist, an error will be displayed on startup of the server.

aetherscale comes with an included HTTP server. While our HTTP implementation
does not allow scaling to multiple machines it simplifies the first steps. You
can start the HTTP server with:

```bash
aetherscale http
```

Once the server is running (on localhost port 5000 in this example) you can
create a new VM from the previously created base image and list all
VMs with:

```bash
curl -XPOST -H "Content-Type: application/json" \
    -d '{"image": "ubuntu-20.04.1-server-amd64"}' http://localhost:5000/vm
curl http://localhost:5000/vm
```

The base image must exist as
`$BASE_IMAGE_FOLDER/ubuntu-20.04.1-server-amd64.qcow2`.

You can also stop a running VM and start a stopped VM by `PATCH`'ing the
VM's REST endpoint with the desired status:

```bash
curl -XPATCH -H "Content-Type: application/json" \
    -d '{"status": "stopped"}' http://localhost:5000/vm/adbvzwdf

curl -XPATCH -H "Content-Type: application/json" \
    -d '{"status": "started"}' http://localhost:5000/vm/adbvzwdf
```

Please note that stopping a VM (gracefully) takes some time, so you cannot
start it immediately after you have issued a stop request.


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

### Creating VMs

When you want to create a new VM, you have to use a *base image*. This is an
already prepared QEMU image in `qcow2` format that will be used to start your
machine.

You can define a custom script that is run on the first start of the machine.
This can be used to install additional software or to configure software.
The init-script is run by systemd and its output can be monitored with

```bash
journalctl -f -u aetherscale-init
```

Execution after the first boot of the machine is prohibited by a conditions
file (cf. in `/etc/systemd/system/aetherscale-init.service`). If you
want to run your script during another boot, you can delete the conditions
file.

## Architecture

My idea is that all requests to the system go through a central message
broker. Handlers will then pick up these tasks and perform the work.

Each request can have the name of a unique channel for responses. The sender
of a message can open a channel with this name on the broker and will receive
responses. This is useful if you have to wait until another component has
performed their work.

### Files created by aetherscale

aetherscale creates different files for VM management in your filesystem.
My goal is to make aetherscale so simple that you can always fix or extend
stuff manually. This section lists all relevant files that aetherscale creates.
The aetherscale configuration directory is a config variable and thus might
be changed. In this section it is refered to as `$CONFIG_DIR`, its default
location is `~/.config/aetherscale`.

For each VM aetherscale creates:

- if required by the VM, networking setup scripts for the VM at
  `$CONFIG_DIR/networking/*-setup.sh` as well as teardown scripts at
  `$CONFIG_DIR/networking/*-teardown.sh`
- a systemd user service file at
  `~/.config/systemd/user/aetherscale-vm-*.service`

TODOs for VM networking:

- TODO: Structure files into subfolders, e.g. `CONFIG/vm/vm-ID/IFACE-setup.sh`?

For each VPN network aetherscale creates:

- a tincd configuration folder structure at
  `$CONFIG_DIR/tinc` with one subfolder per VPN network
- setup and teardown scripts for the host networking rules at
  `$CONFIG_DIR/networking/network-*-setup.sh` and
  `$CONFIG_DIR/networking/network-*-teardown.sh`
- a systemd user service file at
  `~/.config/systemd/aetherscale-tincd-*.service`

TODOs for VPN networking:

- TODO: Rename prefix to `vpn` instead of `network`
- TODO: Structure files into subfolders, e.g. `CONFIG/vpn/vpn-abc/setup.sh`?


### Computing

Stuff I use for computing (and thus have learnt something about so far):

- Qemu
- software bridging with `ip` (for public and private IPs)
  - VDE could also be relevant, but currently out of scope
- layer-2 VPN with tinc
- `libguestfs` for analyzing and changing images
- IPv6, radvd


## Contribution

If you want to contribute you can:

- create some steampunk artwork for this project :)
- think about what else could be interesting to implement (especially if
  it runs as a daemon it should be based on well-established Linux technology
  that runs without babysitting it all day long)
- create a routine for simple setup of the root installation steps
