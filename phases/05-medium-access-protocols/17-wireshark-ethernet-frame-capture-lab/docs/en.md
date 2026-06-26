# Lab: capturing and decoding Ethernet II frames with Wireshark

> A Wireshark capture on a real Ethernet segment is just a wall of hex until you know which bytes are which. This lab makes the link layer legible: the seven-byte `0xAA` preamble plus `0xAB` Start-of-Frame Delimiter, the 6-byte destination and source MAC addresses (with their Individual/Group and Universal/Local flag bits, the OUI vendor prefix, and the broadcast sentinel `ff:ff:ff:ff:ff:ff`), the 2-byte EtherType that selects the next-layer protocol, the up-to-1500-byte payload, and the 4-byte CRC-32 trailer computed with generator polynomial `0x04C11DB7`. You will read frames the way Wireshark reads them, build display filters with `eth.addr`, `eth.type == 0x0800`, and `eth.dst == ff:ff:ff:ff:ff:ff`, drive `tshark -i eth0 -Y 'eth.dst == ff:ff:ff:ff:ff:ff' -T fields -e eth.src -e eth.dst -e eth.type` from the shell, capture with `tcpdump -i eth0 -w capture.pcap`, and dissect a hex string with a small stdlib parser in `code/main.py`. The Ethernet II / IEEE 802.3 distinction is settled by the 0x0600 (1536) rule adopted by IEEE in 1997, and the exercises drill the I/G bit, common EtherTypes (`0x0800` IPv4, `0x0806` ARP, `0x86DD` IPv6, `0x8100` VLAN, `0x8847` MPLS, `0x88CC` LLDP), and the link-layer pane of the pcap-ng file format.

**Type:** Lab
**Languages:** Python, Wireshark, tshark, shell
**Prerequisites:** Ethernet frame format from Tanenbaum §4.3, MAC addressing, IEEE 802.3, basic shell use, basic Wireshark navigation
**Time:** ~90 minutes

## Learning Objectives

- Capture live Ethernet traffic with `tcpdump`/`tshark` and read it back in Wireshark, telling packet list, packet details, and packet bytes panes apart.
- Decode an Ethernet II frame field-by-field: 7-byte preamble, SFD, destination MAC, source MAC, EtherType, payload, pad, FCS (CRC-32 `0x04C11DB7`).
- Classify a destination MAC as unicast, multicast, or broadcast using the I/G bit (LSB of the first byte on the wire) and recognise the U/L bit (second bit on the wire) for locally administered addresses.
- Apply the 0x0600 (1536) Type-vs-Length rule and resolve common EtherTypes (`0x0800`, `0x0806`, `0x86DD`, `0x8100`, `0x8847`, `0x88CC`).
- Run Wireshark display filters and tshark field extractions against the same capture to extract a row-level link-layer report.
- Use a small stdlib Python parser to dissect hex bytes and verify a CRC-32 trailer, reproducing the Wireshark dissection tree without the GUI.

## The Problem

A new network admin opens Wireshark for the first time after a pagercall: "DNS is slow." They click a frame and see `a8:5c:2c:22:c4:7e` in the source column, `00:1b:2b:b1:3f:90` in the destination column, and `0x0800` highlighted in the details pane. The capture also has `33:33:00:00:00:01` rows, a handful of `ff:ff:ff:ff:ff:ff` ARPs, and one entry where the 4-byte tag `0x8100 0x0014` shows up between the source MAC and the EtherType. The admin does not know which fields are which, which bits decode into "multicast", where the OUI vendor lives, why the FCS line is missing, or whether that `0x8100` frame is malformed.

The lesson is to look at L2 first. Ethernet II is the substrate: every other protocol you will see in this course — ARP, IPv4, IPv6, VLAN, MPLS, LLDP, PPPoE — rides on top of this 6+6+2-byte header. If you can read the link layer of a frame, you can name the frame, identify the source/destination, classify the broadcast domain, and choose the correct higher-layer dissector. That is the first habit a good network analyst builds, and it is what this lab teaches.

## The Concept

### The Ethernet II frame on the wire

An Ethernet II frame, in the order the bits appear on the medium, looks like this:

```
+----------+-----+--------+--------+----------+-----------+--------+--------+
| Preamble | SFD |   DA   |   SA   | EtherType|  Payload  |  Pad   |  CRC   |
|  7 bytes | 1 B | 6 B    | 6 B    |  2 B     |  0-1500 B | 0-46 B |  4 B   |
+----------+-----+--------+--------+----------+-----------+--------+--------+
 \____ 8 bytes preamble ____/  \___________ 64-byte minimum DA..FCS ___________/
```

- **Preamble** — seven bytes of `10101010` (`0xAA`). Manchester-encoded at 10 Mbps this becomes a clean 10 MHz square wave that lets the receiver's PLL lock onto the sender's clock. Most NICs strip the preamble before software ever sees the frame.
- **Start-of-Frame Delimiter (SFD)** — one byte `10101011` (`0xAB`). The two trailing `1` bits tell the receiver "frame data starts on the next bit." DIX calls all 8 bytes preamble; 802.3 splits out the last byte as SFD. The parser in `code/main.py` accepts both conventions.
- **Destination Address (DA)** — 6 bytes. First bit transmitted (LSB of byte 0) is the I/G bit; second bit is the U/L bit.
- **Source Address (SA)** — 6 bytes. Always a unicast address (I/G = 0). The first 3 bytes are the OUI assigned by IEEE; the low 3 bytes are the vendor's serial.
- **EtherType** — 2 bytes, big-endian. In Ethernet II this selects the next-layer protocol. In IEEE 802.3 this field is a Length and an LLC/SNAP header sits inside the payload.
- **Payload** — 0 to 1500 bytes. If the actual data is shorter than 46 bytes, the sender appends a Pad to reach the 64-byte minimum.
- **FCS** — 4-byte CRC-32 with generator polynomial `0x04C11DB7`. The receiver drops the frame if the recomputed CRC does not match. Most NICs strip the FCS before delivering the frame to the OS, which is why Wireshark's "packet bytes" pane usually ends at the last byte of the L4 header.

### I/G and U/L: the two first bits

Ethernet sends each byte LSB-first, so the very first bit on the wire is the LSB of byte 0 of the destination address. The first two bits of the destination have a meaning that the textbook often leaves implicit:

| Bit position on the wire | Name | Meaning |
|---|---|---|
| Bit 0 (LSB of byte 0) | I/G (Individual/Group) | 0 = unicast, 1 = group (multicast or broadcast) |
| Bit 1 (next bit)         | U/L (Universal/Local)   | 0 = OUI-assigned (globally unique), 1 = locally administered |

Examples, written with the LSB-first convention Wireshark shows:

| Address (canonical) | First byte hex | I/G | U/L | Classification |
|---|---|---|---|---|
| `a8:5c:2c:22:c4:7e` | `a8 = 1010_1000` | 0 | 0 | Unicast, globally unique, OUI `A8:5C:2C` (Apple) |
| `33:33:00:00:00:01` | `33 = 0011_0011` | 1 | 0 | Multicast, globally unique, IPv6 solicited-node |
| `01:80:c2:00:00:0e` | `01 = 0000_0001` | 1 | 1 | Multicast, locally administered, LLDP (often described as "nearest bridge") |
| `ff:ff:ff:ff:ff:ff` | `ff = 1111_1111` | 1 | 1 | Broadcast — every station accepts it |
| `02:00:00:00:00:01` | `02 = 0000_0010` | 0 | 1 | Unicast but locally administered (no OUI) |

The Source Address is always a unicast (I/G = 0); a frame with the multicast bit set in the source is malformed and silently dropped by most NICs.

### OUI: 24 bits of vendor, 24 bits of serial

The first 3 bytes of any MAC are the OUI (Organizationally Unique Identifier), an IEEE-assigned block of `2^24` addresses. IEEE hands a block to a vendor (Apple, Intel, Cisco, Dell, …), and the vendor programs the low 3 bytes uniquely into every NIC it ships. Two OUIs in `code/main.py`:

| OUI | Vendor |
|---|---|
| `00:1B:2B` | Cisco Systems |
| `A8:5C:2C` | Apple, Inc. |
| `D8:5D:4C` | Dell Inc. |
| `00:11:00` | IBM |
| `00:50:F2` | Microsoft |
| `02:00:00`-`02:BF:FF` | Reserved for locally administered addresses |

The U/L bit (second bit on the wire) is the lever that lets you override the OUI: setting it to 1 means "I am administering this address space myself" — common in virtual machines, containers, and any software-emulated NIC.

### Common EtherTypes you should recognise cold

After the source MAC comes a 2-byte field that the parser interprets using the 0x0600 rule. These are the values you will see most often:

| EtherType | Protocol | Notes |
|---|---|---|
| `0x0800` | IPv4 | The single most common frame on the planet |
| `0x0806` | ARP | "Who has IP X? Tell me your MAC" |
| `0x86DD` | IPv6 | Multicast destination MAC `33:33:xx:xx:xx:xx` is normal |
| `0x8100` | IEEE 802.1Q VLAN | TPID; an additional 2-byte TCI follows, then the real EtherType |
| `0x8847` | MPLS unicast | Carrier / provider networks |
| `0x88CC` | LLDP | Discovery; destination `01:80:c2:00:00:0e` |
| `0x8808` | Ethernet flow control (PAUSE) | Gigabit Ethernet only |
| `0x8863` / `0x8864` | PPPoE Discovery / Session | DSL and some GPON access |
| `0x9000` | ECTP (Configuration Testing) | Loopback test frames |

### Type vs Length: the 0x0600 (1536) rule

DIX (the original 1978 DEC-Intel-Xerox Ethernet) used the field after the source MAC as a Type, telling the OS which network-layer protocol owned the payload. IEEE 802.3 (1983) decided the field would carry the *length* of the payload and bolted an LLC header inside the data to carry the protocol ID. The two formats coexisted for fifteen years until IEEE 802.3x (1997) reconciled them with a single threshold:

> Value ≤ **0x0600 (1536)** is interpreted as **Length** (802.3); value > 0x0600 is **Type** (Ethernet II).

The rule works because every pre-1997 EtherType (`0x0800`, `0x0806`, `0x86DD`, …) is already > 1500, the established maximum payload. Your parser applies the same test and the same interpretation Wireshark does.

### Wireshark's 3-pane view

When you open a capture, Wireshark shows the same frame in three views:

| Pane | What it shows | How to read it |
|---|---|---|
| Packet list | One row per frame with source, destination, protocol, length, time | Use this for navigation and timeline sense |
| Packet details | The dissection tree (Ethernet → IPv4 → TCP → TLS, etc.) | This is where you read fields — click a layer to expand |
| Packet bytes | Raw bytes with the selected field highlighted | This is where you verify the binary encoding |

The SVG for this lab reproduces the 3-pane view and colour-codes the destination MAC, source MAC, and EtherType bytes inside the hex dump so you can match the tree to the wire.

### tshark and tcpdump on the command line

Wireshark is a GUI on top of the same dissector library used by `tshark`. From a shell you can produce the same row-level report without ever opening a window.

```sh
# Live capture on a host interface, write a pcap, also see summary lines
$ tshark -i eth0 -w capture.pcap

# Read the pcap and print only the link-layer columns for IPv4 traffic
$ tshark -r capture.pcap -Y 'eth.type == 0x0800' \
    -T fields -e frame.number -e eth.src -e eth.dst -e eth.type \
    -e ip.src -e ip.dst

# Equivalent tcpdump one-liner that filters while capturing
$ tcpdump -i eth0 -w broadcast.pcap ether dst ff:ff:ff:ff:ff:ff

# Read a pcap with tcpdump and ask for link-layer decode
$ tcpdump -r capture.pcap -nn -e
```

The `-e` flag is the tcpdump equivalent of Wireshark's "packet bytes" pane: it shows the destination MAC, source MAC, EtherType, and length right in the summary line.

### pcap and pcap-ng file formats

The capture file itself is one of:

- **pcap (libpcap)** — the classic 24-byte global header followed by per-packet record headers. Endianness is host-byte order, which makes files non-portable across platforms.
- **pcap-ng** — block-based, self-describing, supports multiple interfaces, comments, name-resolution blocks, and decoupled from the host endianness. The default output of modern Wireshark and `tshark -w` is pcap-ng.

Wireshark can read both. The difference shows up in the "Capture File Properties" dialog, and matters when you write a multi-interface capture or want timestamps with sub-microsecond resolution.

### Wireshark display filters and colouring rules

Display filters are how you say "show me only this" in Wireshark's top-bar filter textbox. The most useful Ethernet ones for this lab:

| Filter | What it shows |
|---|---|
| `eth` | Every Ethernet frame (default) |
| `eth.addr == a8:5c:2c:22:c4:7e` | Frames where the given MAC appears in either address |
| `eth.src == a8:5c:2c:22:c4:7e` | Frames sourced from that MAC |
| `eth.dst == ff:ff:ff:ff:ff:ff` | Only broadcast frames |
| `eth.dst == 01:80:c2:00:00:0e` | Only LLDP multicast |
| `eth.dst[0] & 1` | Every multicast (any group bit set) |
| `eth.type == 0x0800` | Only IPv4 |
| `eth.type == 0x0806` | Only ARP |
| `eth.type == 0x86dd` | Only IPv6 |
| `vlan.id == 20` | Only frames tagged with VLAN 20 |
| `eth.fcs_bad == 1` | Frames whose NIC-reported FCS did not match |
| `frame.len < 64` | Runts (collision debris) — 802.3 minimum |
| `eth.src == eth.dst` | A surprising number of "spurious" issues start here |

Display filters are *not* the same as capture filters (`-f` in tshark / `tcpdump -f`). Display filters run after the capture is loaded and can use the full dissector tree; capture filters run in the kernel BPF engine and have a smaller, byte-oriented syntax. Use the same expressions in `tshark -Y` as you would in the Wireshark filter bar.

## Build It

The Python script `code/main.py` reproduces the Wireshark dissection for the same kinds of frames you would capture. It is stdlib only, has no network calls, and runs in a single `python3` invocation.

1. **MacAddr with I/G and U/L bits** — `MacAddr` stores the six bytes in wire order, exposes the first-transmitted byte and the two flag bits, and classifies the address as unicast, multicast, or broadcast. It also looks the OUI up in a small vendor table and falls back to "Unknown / not in local OUI table" otherwise.
2. **EtherTypeField with the 0x0600 rule** — given the raw 2-byte value, it reports either "Length" or "Type", and looks up the protocol name in `ETHERTYPE_TABLE`. The same 1536 threshold IEEE adopted in 1997 is the test.
3. **EthernetFrame dataclass + parse_frame** — slices a hex string or `bytes` blob into preamble, SFD, destination, source, EtherType/Length, payload, and the 4-byte FCS. It recomputes the CRC-32 with the standard generator `0x04C11DB7` (reflected form `0xEDB88320`) and reports `VALID` / `MISMATCH` in the output. A bad trailer would show up as `[MISMATCH]` — the same red highlight Wireshark uses.
4. **Six demonstration frames** — `_unicast_ipv4`, `_broadcast_arp`, `_multicast_ipv6`, `_vlan_tagged`, `_lldp`, and `_length_8023`. Each builds a real frame, computes a real CRC, and feeds the result to `parse_frame`, so the printed table is what a Wireshark user would see in the details pane.
5. **EtherType reference dump** — the bottom of the run prints a 0x0600 reconciliation table that you can paste into your notes: `0x05DC` (1500) is still Length in old 802.3, `0x0800` is IPv4 Type, `0x86DD` is IPv6 Type, and so on.

Run it from the lesson directory:

```sh
$ python3 code/main.py
```

You should see six dissection tables followed by the Type/Length reference. The frames are deterministic — every run produces the same bytes — so if the parser ever disagrees with Wireshark you have a specific byte to investigate.

## Use It

The bridge from theory to practice is the Wireshark display filter, the tshark one-liner, and the pcap row. Use the table below to predict, then verify, what your own capture will look like.

| Task | Filter / command | What you should see |
|---|---|---|
| Find every IPv4 frame | `eth.type == 0x0800` | Rows whose Protocol column says "IPv4" |
| Find every ARP frame | `eth.type == 0x0806` | Source MAC = sender, dest MAC = `ff:ff:ff:ff:ff:ff` (request) or a unicast (reply) |
| Find every broadcast | `eth.dst == ff:ff:ff:ff:ff:ff` | One row per ARP request, DHCP discover, mDNS, NetBIOS, etc. |
| Find every multicast | `eth.dst[0] & 1` | IPv6, LLDP, OSPF, STP, EIGRP hello frames |
| Find traffic from one host | `eth.src == a8:5c:2c:22:c4:7e` | All frames leaving the Apple laptop |
| Find traffic to a host | `eth.dst == a8:5c:2c:22:c4:7e` | All frames addressed to the Apple laptop |
| Verify a VLAN tag | `vlan.id == 20` | TPID `0x8100` + TCI `0x0014` highlighted between SA and EtherType |
| Spot a bad CRC | `eth.fcs_bad == 1` | NICs that report the FCS (RSS off) will flag the row |
| Find a runt | `frame.len < 64` | Collision debris — fewer than 64 bytes total |
| Per-frame report | `tshark -r capture.pcap -T fields -e eth.src -e eth.dst -e eth.type` | Tab-separated, easy to grep, awk, or import into a spreadsheet |
| Live ARP-only capture | `tshark -i eth0 -Y 'arp' -T fields -e eth.src -e arp.src.proto_ipv4` | One row per ARP frame, source MAC + IPv4 |
| Live broadcast-only capture | `tcpdump -i eth0 -w broadcast.pcap ether dst ff:ff:ff:ff:ff:ff` | A pcap containing only the broadcast traffic — useful for diagnosing storms |

If your output disagrees with the table, the next step is to open the row in the details pane, expand the Ethernet II section, and compare the bytes against the table in this lesson.

## Ship It

Produce one artifact under `outputs/` that proves you can read a frame end-to-end:

- A **frame-dissection cheat sheet** mapping each byte offset (0-13 + payload + last 4 bytes) to its field, with the I/G bit decode, the OUI lookup, and the 0x0600 rule annotated.
- A **tshark/tcpdump field report** generated against a short capture you produced yourself (e.g. `ping`, `curl`, or `arp -a` on a lab host) — paste the command and the first ten rows of output.
- A **CRC-32 + parser verification** — pick one frame, recompute the CRC-32 with the parser, and confirm `[VALID]`. If your NIC strips the FCS, note that and explain why the verification is still meaningful.

Start from `outputs/prompt-wireshark-ethernet-frame-capture-lab.md` if present, or create `outputs/ethernet-ii-frame-reading-guide.md`. Add a short **What good looks like** paragraph at the top so the reader can see the target outcome before they read the body.

## Exercises

1. Capture an ARP request on your lab interface. What is the destination MAC, and is the I/G bit set? Why is ARP's destination the broadcast address rather than a unicast?
2. Capture an IPv4 frame. Identify the EtherType, the first byte of the source MAC, and the OUI of the source. What vendor does the OUI resolve to?
3. Capture a VLAN-tagged frame. Where does the 4-byte 802.1Q tag appear relative to the source MAC and the real EtherType, and what is the VLAN ID?
4. Decode `33:33:00:00:00:01` (the IPv6 solicited-node multicast prefix) as the first-transmitted-bit. Is the address unicast, multicast, or broadcast? Is the I/G bit set? What about `02:00:00:00:00:01`?
5. Use `tshark -r capture.pcap -Y 'eth.type == 0x0806' -T fields -e eth.src -e arp.src.proto_ipv4` against a short capture. How many unique `(mac, ip)` pairs do you see? How does that compare to the rows in your switch's MAC address table?
6. Apply `eth.fcs_bad == 1` against a noisy capture (e.g. a long-running ping flood on a flaky cable). Are there any rows? If not, what does the absence of FCS errors tell you about the link?
7. Run the Python parser against the hex string of a frame you captured (Wireshark → "Copy as Hex Dump"). Confirm the printed dissection matches the Wireshark details pane byte-for-byte.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Ethernet II (DIX) | "Normal Ethernet" | Frame format that uses a Type field > 0x0600 to identify the upper-layer protocol |
| IEEE 802.3 | "Length-based Ethernet" | 802.3 framing with a Length field ≤ 0x0600, usually carrying an LLC/SNAP header inside the payload |
| Preamble + SFD | "The AA bytes" | 7× `0xAA` for clock sync, then `0xAB` SFD whose trailing `11` marks the start of real data |
| I/G bit | "Is it broadcast?" | First bit transmitted of the destination: 0 = unicast, 1 = group (multicast or broadcast) |
| U/L bit | "Is it a virtual MAC?" | Second bit transmitted: 0 = OUI-assigned, 1 = locally administered (overrides the OUI) |
| OUI | "The vendor part" | First 3 bytes of a MAC — an IEEE-assigned `2^24` block identifying the NIC manufacturer |
| EtherType | "The protocol number" | 2-byte big-endian field selecting the next-layer protocol (IPv4, ARP, IPv6, VLAN, MPLS, LLDP, …) |
| 0x0600 rule | "Type or Length?" | IEEE 802.3x (1997) reconciliation: ≤ 1536 = Length, > 1536 = Type |
| FCS | "The CRC" | 4-byte CRC-32 with generator `0x04C11DB7`; bad frames are silently dropped |
| pcap / pcap-ng | "The capture file" | libpcap or block-based self-describing file format that Wireshark/tshark/tcpdump read and write |
| Display filter | "Wireshark's filter bar" | Post-capture selector over the full dissection tree: `eth.type == 0x0800` |
| Capture filter | "BPF filter" | Kernel-side byte-oriented filter used by `tcpdump -f` and `tshark -f` |

## Further Reading

- Wireshark User's Guide — display filters, capture options, 3-pane view, colouring rules: <https://www.wireshark.org/docs/wsug_html/>
- `tshark(1)` man page — `-Y`, `-T fields`, `-e` field reference for every dissector.
- `tcpdump(1)` man page — `-i`, `-w`, `-e`, BPF expression syntax.
- **RFC 894** — "A Standard for the Transmission of IP Datagrams over Ethernet Networks" (DIX framing, EtherType `0x0800`).
- **RFC 1042** — "A Standard for the Transmission of IP Datagrams over IEEE 802 Networks" (LLC/SNAP framing for 802.3).
- **IEEE 802.3-2018** — current Ethernet standard; section 3 / section 4 cover frame format, preamble, and slot time.
- **IEEE 802.1Q-2018** — VLAN tagging: TPID `0x8100`, TCI, VID, PCP, DEI.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.3 — Ethernet framing and MAC addressing (the source chapter for this lesson).
- IEEE OUI registry: <https://standards.ieee.org/products-services/regauth/oui/> — the authoritative source for the OUI → vendor mapping.
