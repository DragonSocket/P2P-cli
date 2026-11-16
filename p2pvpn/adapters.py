"""Linux TAP and UDP I/O adapters. No shell commands or firewall mutations."""
import asyncio
import fcntl
import logging
import os
import socket
import struct
import subprocess

log = logging.getLogger(__name__)


class LinuxConfigurator:
    def configure(self, name, address, mtu):
        for args in (["link", "set", "dev", name, "mtu", str(mtu)],
                     ["addr", "add", address, "dev", name],
                     ["link", "set", "dev", name, "up"]):
            subprocess.run(["ip", *args], check=True, capture_output=True, timeout=5)


class LinuxTap:
    def __init__(self, config, configurator):
        self.config = config
        self.configurator = configurator
        self.fd = None
        self.loop = None

    def open(self, receive, failed):
        if self.config.interface in {item[1] for item in socket.if_nameindex()}:
            raise ValueError("interface already exists; refusing to modify it")
        self.failed = failed
        self.fd = os.open("/dev/net/tun", os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            # No IFF_VNET_HDR / TUNSETOFFLOAD: userspace receives normal frames.
            fcntl.ioctl(self.fd, 0x400454CA, struct.pack("16sH22x", self.config.interface.encode(), 0x0002 | 0x1000))
            self.configurator.configure(self.config.interface, self.config.address, self.config.mtu)
            self.loop = asyncio.get_running_loop()
            self.loop.add_reader(self.fd, self._read, receive)
        except BaseException:
            self.close()
            raise

    def _read(self, receive):
        for _ in range(64):  # Yield to control traffic under sustained load.
            try:
                frame = os.read(self.fd, 2048)
                if not frame:
                    raise OSError("TAP closed")
                receive(frame)
            except BlockingIOError:
                return
            except OSError as exc:
                log.exception("TAP read failed")
                self.close()
                self.failed(exc)
                return

    def write(self, frame):
        if os.write(self.fd, frame) != len(frame):
            raise OSError("partial TAP write")

    def close(self):
        if self.fd is not None:
            if self.loop:
                self.loop.remove_reader(self.fd)
            os.close(self.fd)  # Nonpersistent TAP and its connected route disappear.
            self.fd = None


class NullLink:
    """Discovery-only mode; no pretend packet forwarding."""
    def open(self, receive, failed):
        pass

    def write(self, frame):
        pass

    def close(self):
        pass


class UDPTransport(asyncio.DatagramProtocol):
    def __init__(self, listen):
        host, port = listen.rsplit(":", 1)
        self.address = host, int(port)
        self.transport = None

    async def open(self, receive):
        self.receive = receive
        await asyncio.get_running_loop().create_datagram_endpoint(lambda: self, local_addr=self.address)

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.receive(data, addr)

    def error_received(self, error):
        log.debug("UDP error: %s", error)

    def send(self, packet, address):
        self.transport.sendto(packet, address)

    def close(self):
        if self.transport:
            self.transport.close()
