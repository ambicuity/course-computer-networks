"""Five-layer encapsulation / dissection demo for the book reference model.

Maps the OSI -> TCP/IP -> book (5-layer) model onto a concrete, byte-aware
walk through the stack. We take an HTTP application message and encapsulate it
downward (Application -> Transport -> Network -> Link -> Physical), prepending a
real-ish header at each layer, then dissect it back upward, following the
demultiplexing keys (EtherType, IP Protocol, TCP/UDP port) that a real stack
uses to pick the next handler.

Standard library only. No sockets, no network calls. Run:

    python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# --- Demultiplexing constants (the numbers a stack switches on) ---------------

ETHERTYPE_IPV4 = 0x0800          # IEEE 802.3 / Ethernet II EtherType for IPv4
IP_PROTO_TCP = 6                 # RFC 791 Protocol field value for TCP
IP_PROTO_UDP = 17                # RFC 791 Protocol field value for UDP
IP_PROTO_ICMP = 1                # RFC 791 Protocol field value for ICMP
PORT_HTTP = 80                   # well-known TCP port for HTTP
PORT_DNS = 53                    # well-known UDP port for DNS

PROTO_NAMES = {IP_PROTO_TCP: "TCP", IP_PROTO_UDP: "UDP", IP_PROTO_ICMP: "ICMP"}


# --- Layer headers (only the fields we care about for teaching) ---------------


@dataclass
class EthernetHeader:
    """Link layer (IEEE 802.3). 14-byte header + 4-byte FCS trailer."""

    src_mac: str
    dst_mac: str
    ethertype: int = ETHERTYPE_IPV4

    def fcs(self, payload_len: int) -> int:
        """Toy stand-in for the 32-bit CRC the NIC computes over the frame."""
        return (0xEDB88320 ^ (payload_len * 2654435761)) & 0xFFFFFFFF


@dataclass
class IPv4Header:
    """Network layer (RFC 791). 20-byte minimum header."""

    src_ip: str
    dst_ip: str
    protocol: int
    ttl: int = 64
    df_bit: bool = True

    def checksum(self, payload_len: int) -> int:
        """Toy 16-bit one's-complement-style checksum over header fields."""
        octets = [int(p) for p in self.src_ip.split(".")]
        octets += [int(p) for p in self.dst_ip.split(".")]
        total = self.ttl + self.protocol + payload_len + sum(octets)
        return (~total) & 0xFFFF


@dataclass
class TCPHeader:
    """Transport layer (RFC 9293). 20-byte minimum header."""

    src_port: int
    dst_port: int
    seq: int
    ack: int = 0
    syn: bool = True
    ack_flag: bool = False
    window: int = 64240

    def flag_str(self) -> str:
        flags = []
        if self.syn:
            flags.append("SYN")
        if self.ack_flag:
            flags.append("ACK")
        return "|".join(flags) or "(none)"


@dataclass
class UDPHeader:
    """Transport layer (RFC 768). 8-byte fixed header."""

    src_port: int
    dst_port: int
    length: int


@dataclass
class Frame:
    """A fully encapsulated five-layer unit, built top-down."""

    eth: EthernetHeader
    ip: IPv4Header
    transport: object  # TCPHeader | UDPHeader
    app_payload: bytes
    log: list[str] = field(default_factory=list)


# --- Encapsulation: descend the stack -----------------------------------------


def encapsulate(
    http_message: str,
    *,
    src_mac: str,
    dst_mac: str,
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    use_udp: bool = False,
) -> Frame:
    """Wrap an application message down through all five book layers."""
    log: list[str] = []
    payload = http_message.encode("ascii")

    log.append(f"[L5 Application] message = {http_message.splitlines()[0]!r} "
               f"({len(payload)} bytes)")

    if use_udp:
        proto = IP_PROTO_UDP
        transport: object = UDPHeader(src_port, dst_port, length=8 + len(payload))
        log.append(f"[L4 Transport ] UDP datagram src={src_port} dst={dst_port} "
                   f"len={8 + len(payload)} -> IP Protocol={proto}")
    else:
        proto = IP_PROTO_TCP
        transport = TCPHeader(src_port, dst_port, seq=1_000, syn=False, ack_flag=True)
        log.append(f"[L4 Transport ] TCP segment src={src_port} dst={dst_port} "
                   f"flags={transport.flag_str()} -> IP Protocol={proto}")

    ip = IPv4Header(src_ip, dst_ip, protocol=proto)
    csum = ip.checksum(len(payload))
    log.append(f"[L3 Network   ] IPv4 {src_ip} -> {dst_ip} ttl={ip.ttl} "
               f"proto={PROTO_NAMES[proto]} checksum=0x{csum:04X} -> EtherType=0x{ETHERTYPE_IPV4:04X}")

    eth = EthernetHeader(src_mac, dst_mac)
    fcs = eth.fcs(len(payload))
    log.append(f"[L2 Link      ] Ethernet {src_mac} -> {dst_mac} "
               f"ethertype=0x{eth.ethertype:04X} fcs=0x{fcs:08X}")

    total_bits = (14 + 20 + (8 if use_udp else 20) + len(payload) + 4) * 8
    log.append(f"[L1 Physical  ] serialize frame as {total_bits} bits on the wire")

    return Frame(eth=eth, ip=ip, transport=transport, app_payload=payload, log=log)


# --- Dissection: ascend the stack, following demux keys -----------------------


def dissect(frame: Frame) -> list[str]:
    """Unwrap a frame upward, choosing the next handler by demux key."""
    out: list[str] = []

    out.append("[L1 Physical  ] received bits, framed by NIC")

    # Link: read EtherType to demux to the network layer.
    if frame.eth.ethertype == ETHERTYPE_IPV4:
        out.append(f"[L2 Link      ] dst_mac={frame.eth.dst_mac} "
                   f"EtherType=0x{frame.eth.ethertype:04X} -> dispatch to IPv4")
    else:
        out.append(f"[L2 Link      ] unknown EtherType 0x{frame.eth.ethertype:04X}, drop")
        return out

    # Network: read Protocol to demux to the transport layer.
    proto = frame.ip.protocol
    out.append(f"[L3 Network   ] {frame.ip.src_ip} -> {frame.ip.dst_ip} "
               f"ttl={frame.ip.ttl} Protocol={proto} -> dispatch to {PROTO_NAMES.get(proto, '??')}")
    if frame.ip.ttl <= 0:
        out.append("[L3 Network   ] TTL expired -> would emit ICMP Time Exceeded (Type 11)")
        return out

    # Transport: read dest port to demux to the application.
    t = frame.transport
    if isinstance(t, TCPHeader):
        out.append(f"[L4 Transport ] TCP seq={t.seq} flags={t.flag_str()} "
                   f"dst_port={t.dst_port} -> dispatch by port")
        dport = t.dst_port
    elif isinstance(t, UDPHeader):
        out.append(f"[L4 Transport ] UDP len={t.length} dst_port={t.dst_port} -> dispatch by port")
        dport = t.dst_port
    else:
        out.append("[L4 Transport ] unknown transport, drop")
        return out

    app = {PORT_HTTP: "HTTP", PORT_DNS: "DNS"}.get(dport, f"port {dport}")
    out.append(f"[L5 Application] {app}: {frame.app_payload.decode('ascii').splitlines()[0]!r}")
    return out


def route_one_hop(frame: Frame, next_hop_mac: str, my_mac: str) -> Frame:
    """Simulate what a layer-3 router does at one hop.

    Chained layers (Link rewrite, Network TTL/checksum) change; the end-to-end
    transport header is left byte-for-byte intact.
    """
    new_ip = IPv4Header(frame.ip.src_ip, frame.ip.dst_ip, frame.ip.protocol,
                        ttl=frame.ip.ttl - 1, df_bit=frame.ip.df_bit)
    new_eth = EthernetHeader(src_mac=my_mac, dst_mac=next_hop_mac,
                            ethertype=frame.eth.ethertype)
    # transport + payload deliberately reused unchanged (end-to-end invariant).
    return Frame(eth=new_eth, ip=new_ip, transport=frame.transport,
                 app_payload=frame.app_payload)


# --- Demonstration ------------------------------------------------------------


def banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main() -> None:
    http = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"

    banner("ENCAPSULATION  (book model: App -> Transport -> Network -> Link -> Phys)")
    frame = encapsulate(
        http,
        src_mac="02:42:ac:11:00:02",
        dst_mac="02:42:ac:11:00:01",
        src_ip="10.0.0.7",
        dst_ip="93.184.216.34",
        src_port=51514,
        dst_port=PORT_HTTP,
    )
    for line in frame.log:
        print("  " + line)

    banner("ROUTER HOP  (chained L1-L3 rewritten, end-to-end L4 untouched)")
    seq_before = frame.transport.seq if isinstance(frame.transport, TCPHeader) else None
    hopped = route_one_hop(frame, next_hop_mac="02:42:ac:11:00:fe", my_mac="02:42:ac:11:00:01")
    print(f"  TTL  {frame.ip.ttl} -> {hopped.ip.ttl}  (Network layer decremented)")
    print(f"  src MAC {frame.eth.src_mac} -> {hopped.eth.src_mac}  (Link layer rewritten)")
    seq_after = hopped.transport.seq if isinstance(hopped.transport, TCPHeader) else None
    print(f"  TCP seq {seq_before} -> {seq_after}  (Transport layer UNCHANGED: end-to-end)")

    banner("DISSECTION  (receiver peels headers, follows demux keys upward)")
    for line in dissect(hopped):
        print("  " + line)

    banner("CONTRAST: same payload over UDP/53 (DNS)")
    dns_frame = encapsulate(
        "QUERY example.com A?",
        src_mac="02:42:ac:11:00:02",
        dst_mac="02:42:ac:11:00:01",
        src_ip="10.0.0.7",
        dst_ip="8.8.8.8",
        src_port=40000,
        dst_port=PORT_DNS,
        use_udp=True,
    )
    for line in dissect(dns_frame):
        print("  " + line)


if __name__ == "__main__":
    main()
