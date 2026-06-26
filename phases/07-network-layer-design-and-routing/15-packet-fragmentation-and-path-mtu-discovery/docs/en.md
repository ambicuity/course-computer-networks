# Packet Fragmentation and Path MTU Discovery

> Every link in a network path has a maximum frame size; when an IP packet is larger than any link it must cross, the network must either fragment it or discover the constraint ahead of time — and the choice between those two strategies defines whether reassembly happens inside the network or only at the destination.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** IPv4 header format, IP forwarding basics, network layer design issues
**Time:** ~75 minutes

## Learning Objectives

- Explain why different network technologies impose different maximum packet sizes and list at least four causes.
- Contrast transparent (in-network) fragmentation with nontransparent (end-to-end) fragmentation and identify which strategy IP uses.
- Describe exactly how IPv4 represents fragments using the Identification, Fragment Offset, and More Fragments flag fields, and reassemble a fragmented packet from those fields.
- Explain path MTU discovery (RFC 1191): how the DF bit, ICMP "Destination Unreachable / fragmentation needed" messages, and source-side re-fragmentation interact.
- Compute fragment boundaries and offsets for an arbitrary original packet size and path MTU.
- Identify the performance costs of fragmentation (header overhead, whole-packet loss on fragment loss) and explain why modern stacks prefer path MTU discovery.

## The Problem

A supercomputer at a university generates 8 KB scientific data transfers as single IP datagrams. The packets leave the campus over a Gigabit Ethernet link (MTU 1500 bytes), cross a WAN segment that accepts up to 4470 bytes, and finally arrive at a partner institution through a legacy tunnel whose inner MTU is only 1280 bytes. The application has no idea these links exist.

On the first transfer, packets larger than 1280 bytes are silently discarded at the tunnel router. The application retransmits. The retransmitted packet is fragmented at the WAN router into three pieces. One fragment is lost in a congestion event. The entire original datagram must be retransmitted because IP reassembly requires all fragments — there is no partial delivery. Performance collapses: a 10 MB file transfer that should complete in under a second stalls for minutes.

The root cause is the application and transport layer being unaware of the tightest link in the path. Understanding fragmentation mechanics — and why path MTU discovery exists to eliminate mid-network fragmentation — is essential for diagnosing this class of silent failure.

## The Concept

### Why MTUs Differ

Every network technology imposes a maximum packet (payload) size on the frames it carries. The limits come from different sources:

| Cause | Example |
|-------|---------|
| Hardware DMA buffer size | Early Ethernet NICs |
| OS kernel buffer granularity | 512-byte buffer pages |
| Protocol field width | IP total length is 16 bits → max 65,535 bytes |
| National/international standards compliance | X.25, ATM cells |
| Retransmission economics | Smaller packets → less wasted bandwidth per error |
| Channel fairness | Prevent one flow from monopolizing a shared link |

Common MTU values:

| Technology | MTU (bytes) |
|------------|-------------|
| Ethernet (IEEE 802.3) | 1500 |
| IEEE 802.11 (Wi-Fi) | 2272 |
| IPv6 minimum | 1280 |
| IPv4 minimum routers must forward | 576 (old) / 1280 (modern) |
| IP maximum (theoretical) | 65,515 (IPv4) |
| Jumbo frames (Ethernet, optional) | 9000 |

### IPv4 Fragmentation Fields

IPv4 was designed to handle packets larger than any intermediate link. Three fields in the IPv4 header manage fragmentation:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Version  |  IHL  |    DSCP   |ECN|        Total Length       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Identification        |Flags|      Fragment Offset    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Identification (16 bits):** A unique value assigned to the original datagram. All fragments of the same datagram carry the same Identification value. This is how the destination knows which buffer to place each fragment into.
- **Flags (3 bits):**
  - Bit 0: Reserved (must be 0)
  - Bit 1: **DF** (Don't Fragment) — if set, routers must not fragment this packet; drop it and send ICMP error instead
  - Bit 2: **MF** (More Fragments) — set in all fragments except the last
- **Fragment Offset (13 bits):** Byte offset of this fragment's data within the original datagram, measured in units of **8 bytes**. The maximum offset is 2¹³ − 1 = 8191 units × 8 = 65,528 bytes.

### Transparent vs. Nontransparent Fragmentation

Two strategies exist:

```
Transparent (OSI, old X.25):

  [Large packet]
       |
   Router G1 ── fragments ──> [frag1][frag2][frag3]
                                        |
                               Router G2 ── reassembles ──> [Large packet]
                                        |
                               Next network (unaware fragmentation happened)

Nontransparent (IP):

  [Large packet]
       |
   Router G1 ── fragments ──> [frag1][frag2][frag3]
       |                            each forwarded independently
       |                            may take different routes
       v
   Destination host ── reassembles ──> [Original packet]
```

**IP uses nontransparent fragmentation.** Routers do less work; fragments can take different paths; no intermediate router needs to buffer and track fragment sets. The cost: the destination must buffer all fragments and reassemble, and if any fragment is lost, the entire datagram must be retransmitted.

### Fragment Offset Arithmetic

Consider an original IPv4 packet with 20-byte header and 1400 bytes of data (Total Length = 1420), passing through a link with MTU = 620 bytes.

Maximum data per fragment = 620 − 20 (IP header) = 600 bytes.
600 must be a multiple of 8 → floor(600/8) × 8 = 600 bytes (already aligned).

```
Fragment 1:
  Total Length  = 20 + 600 = 620
  Flags         = MF=1, DF=0
  Fragment Offset = 0 / 8 = 0

Fragment 2:
  Total Length  = 20 + 600 = 620
  Flags         = MF=1, DF=0
  Fragment Offset = 600 / 8 = 75

Fragment 3 (remainder):
  Data          = 1400 - 600 - 600 = 200 bytes
  Total Length  = 20 + 200 = 220
  Flags         = MF=0, DF=0   ← last fragment
  Fragment Offset = 1200 / 8 = 150
```

Reassembly at the destination: allocate a 1400-byte buffer (learned from the last fragment's offset + its data size). Place fragment data at byte offset = Fragment Offset × 8. Set a bit in a reassembly bitmap. When all bits are set and MF=0 fragment is received, reassembly is complete.

### Fragments Can Be Re-fragmented

If a fragment passes over a network with an even smaller MTU, it can itself be fragmented. The Identification field is preserved; Fragment Offset values of the sub-fragments are computed relative to the original datagram's start. The destination always reconstructs the original from Identification + Fragment Offset without knowing how many times fragmentation occurred.

```
Original: ID=27, Offset=0, MF=0, data bytes A-J (10 bytes)

After MTU=8+header:
  ID=27, Offset=0, MF=1, data A-H
  ID=27, Offset=1, MF=0, data I-J     (offset = 8/8 = 1)

After re-fragmentation at MTU=5+header:
  ID=27, Offset=0, MF=1, data A-E
  ID=27, Offset=5, MF=1, data F-H     (offset = 40/8, but with 1-byte units this is offset=5/8=0... wait)
```

In practice, fragment offsets are in 8-byte units so all fragment data sizes must be multiples of 8 (except the last fragment). This is the alignment requirement.

### Path MTU Discovery (RFC 1191)

Path MTU discovery eliminates mid-network fragmentation entirely. The strategy:

1. Source sets the **DF (Don't Fragment) bit** in every packet.
2. If a router receives a packet larger than its outgoing link's MTU and DF=1, it **drops the packet** and sends back an ICMP Type 3 (Destination Unreachable), Code 4 ("fragmentation needed and DF set") message. The ICMP message includes the MTU of the constraining link (added in RFC 1191; not in the original ICMP spec).
3. The source receives the ICMP error, learns the new MTU ceiling, reduces its packet size, and retransmits.
4. If a further router down the path also has a smaller MTU, the process repeats.

```
Source          Router R1         Router R2         Destination
  |                |                  |                  |
  |-- pkt 1400 -->|                  |                  |
  |               | MTU=1200         |                  |
  |               | DF=1, too big    |                  |
  |<-- ICMP "try 1200" --|           |                  |
  |                |                  |                  |
  |-- pkt 1200 -->|-- pkt 1200 ---->|                  |
  |               |                  | MTU=900          |
  |               |                  | DF=1, too big    |
  |<------------- ICMP "try 900" ---|                  |
  |                |                  |                  |
  |-- pkt 900 -->|-- pkt 900 ----->|-- pkt 900 ------>|
```

The source caches the path MTU per destination. TCP uses this cached value to set its MSS (Maximum Segment Size), so fragmentation never occurs for that connection.

**Startup cost:** Path MTU discovery may require 2–3 round trips before the first data reaches the destination. For short-lived connections (DNS, HTTP/1.0), this is significant overhead.

**ICMP filtering problem:** Some firewalls block all ICMP. When ICMP Type 3 Code 4 is filtered, the source never learns the path MTU. DF=1 packets are silently dropped. The connection appears to hang ("black hole"). This is the "PMTU black hole" failure mode. Workaround: PMTUD over TCP uses the MSS option to negotiate a safe segment size, and some stacks implement "PMTU black hole detection" by retrying with DF=0 after a timeout.

## Build It

The following Python script (`code/main.py`) implements fragment encoder and path MTU prober logic:

```python
import struct
import socket
import random

IPV4_HEADER_LEN = 20

def fragment_packet(identification, total_data, path_mtu):
    """
    Simulate IPv4 fragmentation of a datagram with `total_data` bytes of payload.
    Returns list of (frag_offset_bytes, data_length, mf_bit) tuples.
    """
    max_data = path_mtu - IPV4_HEADER_LEN
    # Fragment data must be a multiple of 8, except for the last fragment
    max_data = (max_data // 8) * 8
    if max_data <= 0:
        raise ValueError(f"MTU {path_mtu} too small for IP header")

    fragments = []
    offset = 0
    remaining = total_data

    while remaining > 0:
        chunk = min(max_data, remaining)
        mf = 1 if remaining > chunk else 0
        fragments.append({
            'id': identification,
            'offset_bytes': offset,
            'offset_field': offset // 8,   # as stored in IPv4 header (8-byte units)
            'data_len': chunk,
            'mf': mf,
            'total_len': IPV4_HEADER_LEN + chunk,
        })
        offset += chunk
        remaining -= chunk

    return fragments

def reassemble(fragments):
    """
    Given fragments (sorted or unsorted), reassemble and return total data length.
    Validates that offsets are consistent and MF bits are correct.
    """
    sorted_frags = sorted(fragments, key=lambda f: f['offset_bytes'])
    expected_offset = 0
    total = 0
    for i, frag in enumerate(sorted_frags):
        assert frag['offset_bytes'] == expected_offset, (
            f"Gap at offset {expected_offset}, got {frag['offset_bytes']}"
        )
        expected_offset += frag['data_len']
        total += frag['data_len']
        is_last = (i == len(sorted_frags) - 1)
        assert (frag['mf'] == 0) == is_last, "MF bit inconsistent"
    return total

def simulate_path_mtu_discovery(original_size, path_mtus):
    """
    Simulate PMTUD: source tries decreasing sizes until packet fits entire path.
    path_mtus: list of MTUs at each hop (simulating a series of routers).
    Returns the discovered path MTU.
    """
    current_size = original_size
    print(f"Source trying packet size: {current_size}")
    for i, mtu in enumerate(path_mtus):
        if current_size > mtu:
            print(f"  Router hop {i+1}: MTU={mtu}, packet too large (DF=1) → ICMP back")
            current_size = mtu
            print(f"  Source retrying with size: {current_size}")
    print(f"Path MTU discovered: {current_size}")
    return current_size

if __name__ == '__main__':
    # Example 1: Fragment a 1420-byte datagram over a 620-byte MTU path
    print("=== Fragmentation Example ===")
    frags = fragment_packet(identification=0xABCD, total_data=1400, path_mtu=620)
    for f in frags:
        print(f"  ID={f['id']:#06x}  offset={f['offset_bytes']:5d}B "
              f"(field={f['offset_field']:4d})  data={f['data_len']:4d}B  "
              f"MF={f['mf']}  total_len={f['total_len']}")
    recovered = reassemble(frags)
    print(f"  Reassembled: {recovered} bytes (original data: 1400 bytes) ✓\n")

    # Example 2: Re-fragmentation
    print("=== Re-fragmentation Example ===")
    frags2 = fragment_packet(identification=0x1234, total_data=1400, path_mtu=800)
    print(f"  After MTU=800: {len(frags2)} fragments")
    # Re-fragment first fragment over MTU=500
    sub_frags = []
    for f in frags2:
        if f['total_len'] > 500:
            sf = fragment_packet(f['id'], f['data_len'], path_mtu=500)
            # Adjust offsets relative to original
            for s in sf:
                s['offset_bytes'] += f['offset_bytes']
                s['offset_field'] = s['offset_bytes'] // 8
            sub_frags.extend(sf)
        else:
            sub_frags.append(f)
    print(f"  After re-fragmentation at MTU=500: {len(sub_frags)} total fragments")

    # Example 3: Path MTU discovery simulation
    print("\n=== Path MTU Discovery ===")
    simulate_path_mtu_discovery(
        original_size=1400,
        path_mtus=[1500, 1200, 900, 900]
    )
```

Run with:
```
python3 code/main.py
```

No external dependencies required.

## Use It

| Task | What to observe |
|------|-----------------|
| Fragmentation of a 1400-byte datagram over MTU=620 | 3 fragments; first two have MF=1, last has MF=0; offsets are 0, 600, 1200 |
| Reassembly validation | `reassemble()` asserts no gaps and correct MF bits |
| Re-fragmentation | Fragment count increases; original Identification preserved; offsets grow monotonically |
| PMTUD simulation | Source shrinks packet size on each ICMP notification until fitting smallest MTU |
| Wireshark trace | Filter `ip.flags.df == 1` to find PMTUD probes; `icmp.type == 3 && icmp.code == 4` for "frag needed" errors |

In a real Wireshark capture of a large file transfer, filter `ip.id == <value>` to track all fragments of one datagram. The Fragment Offset column (in the "Internet Protocol" tree) shows each fragment's position in 8-byte units.

## Ship It

Run and save the fragmentation analysis for a typical 1500-byte Ethernet MTU scenario:

```bash
python3 code/main.py > outputs/fragmentation-demo.txt
```

Runbook snippet — diagnose a PMTU black hole on Linux:

```bash
# Send a DF=1 probe of increasing sizes to find the path MTU to a host
for size in 1500 1400 1300 1200 1000; do
    ping -M do -s $((size - 28)) -c 1 -W 2 <destination_ip> 2>&1 \
      | grep -E "bytes from|Frag needed|unreachable" \
      && echo "MTU >= $size works" || echo "MTU $size BLOCKED"
done

# On macOS:
# ping -D -s $((size - 28)) -c 1 <destination_ip>
```

This iterates from large to small, identifying the largest packet size that reaches the destination with DF=1 set.

## Exercises

1. **Offset arithmetic:** An IPv4 datagram has a 20-byte header and 3000 bytes of data. It must cross a link with MTU = 1000 bytes. Compute the number of fragments, the Fragment Offset value stored in the header (in 8-byte units), the MF bit, and the Total Length for each fragment.

2. **Re-fragmentation trace:** Using the output of `code/main.py`, take the first fragment produced at MTU=800 and manually verify that re-fragmenting it at MTU=500 produces correct offset values relative to the original datagram. What is the Fragment Offset field value (in 8-byte units) of the second sub-fragment?

3. **PMTU black hole diagnosis:** A TCP connection between two hosts appears to hang after the 3-way handshake but never transfers data. Both hosts can ping each other with small packets. The path includes a firewall that blocks all ICMP. Explain step by step what happens at each layer. What kernel tunable on Linux (`ip route` or `sysctl`) can mitigate this without requiring firewall changes?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| MTU | "the max packet size" | Maximum Transmission Unit: the largest IP datagram payload a network technology can carry in a single frame |
| Path MTU | "the bottleneck MTU" | The smallest MTU of any link on the end-to-end path; determines the largest unfragmented packet the source can send |
| DF bit | "don't fragment flag" | IPv4 header flag bit 1; when set, routers must drop the packet rather than fragment it |
| MF bit | "more fragments flag" | IPv4 header flag bit 2; set in all fragments except the last one |
| Fragment Offset | "the offset field" | 13-bit IPv4 header field; byte position of this fragment's data within the original datagram, in units of 8 bytes |
| Identification | "the fragment ID" | 16-bit IPv4 header field; same value in all fragments of the same original datagram; used by destination to group fragments |
| Transparent fragmentation | "router reassembly" | Strategy where an intermediate router both fragments and reassembles; hides fragmentation from the rest of the path; not used by IP |
| Nontransparent fragmentation | "end-to-end fragmentation" | Strategy where fragments are forwarded independently and reassembled only at the destination; used by IPv4 |
| Path MTU discovery | "PMTUD" | RFC 1191 mechanism: source sets DF=1, learns path MTU from ICMP "fragmentation needed" errors, adjusts packet size |
| PMTU black hole | "ICMP filtering stall" | Failure mode where firewalls block ICMP Type 3 Code 4, causing DF=1 packets to be silently dropped with no feedback to the source |

## Further Reading

- **RFC 791** (1981) — Internet Protocol; Section 2.3 (Fragmentation and Reassembly) defines the Identification, Flags, and Fragment Offset fields.
- **RFC 1191** (1990) — Path MTU Discovery (Mogul and Deering); defines the DF-bit-plus-ICMP mechanism and the "next-hop MTU" field in ICMP messages.
- **RFC 1981** (1996) — Path MTU Discovery for IP version 6; IPv6 does not allow router fragmentation at all; only source hosts may fragment.
- **RFC 2923** (2000) — TCP Problems with Path MTU Discovery; documents PMTU black hole detection and workarounds.
- Kent, S. and Mogul, J., "Fragmentation Considered Harmful," *ACM SIGCOMM Computer Communication Review*, 1987 — the paper that argued fragmentation should be avoided in the network; motivated path MTU discovery.
- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., Section 5.5.5 (Packet Fragmentation) and Section 5.6.1 (IPv4).
