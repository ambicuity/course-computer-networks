# NetFlow/IPFIX export and flow-based traffic accounting

> At 02:14 UTC your edge router pushes a 250 kpps DDoS at the /24 hosting `api.example.com`. Your SNMP poller shows the link at 92% but cannot tell which /32 is hot. You need NetFlow v9 (RFC 3954) or IPFIX (RFC 7011, RFC 5103) — sampled at 1-in-1000 with the same flow mask as the upstream provider — to answer "who is sending to whom, which TCP flag, which DSCP, since when?". This lesson builds a one-router / two-host topology, exports IPFIX over UDP/4739 with `nfacctd` → `nfcapd`, parses the resulting `.nfcap` file, and ships a 7-day accounting report. The companion `code/main.py` is an offline NetFlow/IPFIX template parser: it reads the variable-length template records (header, flowset, record fields, scoped enterprise numbers), supports both v5 fixed templates and v9/IPFIX variable templates, and produces a billing-style record per (src, dst, proto, port, dscp) tuple — exactly the same accounting the carrier bills you on.

**Type:** Lab
**Languages:** Python, shell, nfcapd, tcpdump
**Prerequisites:** Phase 09 IPv4/IPv6 basics, Phase 08 QoS DSCP primer, ability to read a pcap with `tcpdump`
**Time:** ~75 minutes

## Learning Objectives

- Build a 4-node lab (`collector`, `exporter`, `h1`, `h2`) using Linux network namespaces, route traffic through `exporter`, and turn on `nfacctd` to mirror a flow into `nfcapd`.
- Read a NetFlow v9 and IPFIX packet from scratch: 16-bit version, 16-bit count, 32-bit SysUptime, 32-bit UNIX seconds, 32-bit sequence number, 6-byte source ID — then the sequence of (template, data) flowsets each carrying the Information Element IDs from IANA's IPFIX registry.
- Explain why sampling matters: 1-in-1000 with random sampling (RFC 5475) gives a 0.1% accuracy envelope at 1/1000th the collector load — and why "every packet" only matters when the cost of missing a flow exceeds the cost of exporting it.
- Use `code/main.py` to parse a synthetic IPFIX record and produce per-flow octet/byte accounting, identifying the top talker by `(src, dst, dscp)` tuple.
- Verify the export by capturing the UDP/4739 packets with `tcpdump -nn -i any port 4739` and confirming the (version, count, SysUptime, sequence) header aligns with what `nfcapd` writes to disk.
- Differentiate NetFlow v5 (fixed 7-record template, 48-byte payload) from v9 (variable templates) and IPFIX (RFC 7011 with vendor-specific Information Element IDs ≥ 32768).

## The Problem

The edge router is congested but `top` on the router box is fine and `ifconfig` shows zero errors. The issue is not on a single interface — it is on a single conversation. Per-packet `tcpdump` is the right tool for one flow but generates gigabytes per minute at line rate; you cannot pcap the WAN link for an hour. You need flow telemetry: a compact per-flow summary the router streams to a collector that you can query on demand.

The trap most teams fall into is conflating "monitoring" with "metering". SNMP gives you the ifInOctets counter; NetFlow/IPFIX gives you the conversation. For 99% of operational questions — top talkers, per-tenant billing, traffic matrices, anomaly detection — you need flow data, not packet data. The cost is exporting every flow record (or a 1-in-N sample) and the discipline of managing templates.

## The Concept

### What a flow actually is

A **flow** is a unidirectional sequence of packets sharing a key. The classical 5-tuple is `(src IP, dst IP, src port, dst port, IP protocol)` (Claise, RFC 5101). NetFlow v5 fixes this 5-tuple plus ingress interface and IP/AS next-hop. NetFlow v9 and IPFIX (RFC 7011) generalize the key: any Information Element (IE) from IANA's registry (https://www.iana.org/assignments/ipfix/ipfix.xhtml) can be part of the key, and any other IE can be a non-key field. Examples of non-key fields: packet count, octet count, TCP flags OR-mask, flow start/end SysUptime, BGP next-hop AS, MPLS label, IPv6 extension headers.

### The two record types — v5 fixed vs v9/IPFIX variable

NetFlow v5 has a single fixed-format record: 48 bytes per flow entry, 7 fields, no options. The header is 24 bytes; the payload is always 30 records × 48 bytes. v5 is simple, supported by every router that has "NetFlow" in the datasheet, but it cannot carry new fields without firmware changes.

NetFlow v9 (RFC 3954) introduced **templates**: the exporter sends a Template Record describing the field layout, then Data Records carrying that layout. The collector caches templates by `(template_id, source_id)`. IPFIX (RFC 7011) standardized the same model and added **Options Templates** (RFC 5101) for non-flow data (sampling rate, exporter health), bidirectional flows (BIF, RFC 5103), and variable-length Information Elements (e.g., BGP communities, MPLS labels). The Information Element ID space starts at 32768 for enterprise-specific elements (your router vendor uses 32768–65535).

### Packet structure

A v9 / IPFIX UDP datagram starts with:

```
0                   1                   2                   3
0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Version Number          |            Length             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      Export Time (UNIX sec)   |   Sequence Number             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|             Observation Domain ID (Source ID)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Then a sequence of flowsets, each prefixed with its own `(FlowSet ID, Length)` header. FlowSet ID `2` = Template Set, `3` = Options Template (IPFIX), ≥ `256` = Data Set keyed by template ID.

The 24-byte IPFIX header adds two flags beyond v9: the **Exporting Process** ID byte and a **Length** field for the whole message (RFC 7011 §10). NetFlow v9 uses 24 bytes too, but without the version ≥ 10 distinction; `version=10` is IPFIX, `version=9` is NetFlow v9.

### Sampling and its pitfalls

A 10 Gbps link at full chat pushes 14.8 Mpps; exporting a flow per 5-tuple at 1 Gbps of new flows per second saturates the collector. The IETF PSAMP Working Group (RFC 5474, RFC 5475) standardized packet sampling: the router marks 1 in N outgoing flow records with `samplingInterval` (option template 256 / 257). Two failure modes:

1. **Out-of-order packets.** Sampled flows may arrive at the collector out of order. The collector must buffer by sequence number — never trust a single record's timestamp in isolation.
2. **False zeros.** At 1-in-1000 sampling, a small /32 that sends 50 flows per minute shows 0–2 records per minute. Threshold-based alerting ("alert if traffic > 1 Mbps") must scale the sample rate, or it produces false positives on the tail.

### Why UDP and not TCP

Flow export uses UDP (default port 2055 for v5, 9995 for v9, 4739 for IPFIX) and that is deliberate. TCP would mean head-of-line blocking on a congested link, retransmits that double-count in billing, and a per-exporter session state that does not survive a router reload. UDP/4739 is stateless from the exporter's perspective: if the collector is down, the exporter drops records and increments `nfexp_drops`. Production operators watch `nfexp_drops` as a primary metric — the same way they watch `snmp ifInDiscards`.

### What the collector does

`nfcapd` (from the nfdump toolchain) listens on UDP/4739, buffers to a rotating `.nfcap` file keyed by the timestamp, and rolls over every 5 minutes by default. `nfdump -R /var/netflow/data -c 100` reads the files and prints the top 100 flows by octets/packets/duration. The 5-minute rotation matters: it aligns with SLA reporting, billing windows, and SRE on-call shifts.

## Build It

### Step 1: Build the 4-node lab

```bash
ip netns add collector
ip netns add exporter
ip netns add h1
ip netns add h2

ip link add veth-c-e type veth peer name veth-e-c
ip link set veth-c-e netns collector
ip link set veth-e-c netns exporter
ip netns exec collector ip addr add 10.10.0.1/30 dev veth-c-e
ip netns exec collector ip link set veth-c-e up
ip netns exec exporter ip addr add 10.10.0.2/30 dev veth-e-c
ip netns exec exporter ip link set veth-e-c up

ip link add veth-e-1 type veth peer name veth-1-e
ip link set veth-e-1 netns exporter
ip link set veth-1-e netns h1
ip netns exec exporter ip addr add 10.10.1.1/30 dev veth-e-1
ip netns exec exporter ip link set veth-e-1 up
ip netns exec h1 ip addr add 10.10.1.2/30 dev veth-1-e
ip netns exec h1 ip link set veth-1-e up
ip netns exec h1 ip route add default via 10.10.1.1

ip link add veth-e-2 type veth peer name veth-2-e
ip link set veth-e-2 netns exporter
ip link set veth-2-e netns h2
ip netns exec exporter ip addr add 10.10.2.1/30 dev veth-e-2
ip netns exec exporter ip link set veth-e-2 up
ip netns exec h2 ip addr add 10.10.2.2/30 dev veth-2-e
ip netns exec h2 ip link set veth-2-e up
ip netns exec h2 ip route add default via 10.10.2.1

ip netns exec exporter sysctl -w net.ipv4.ip_forward=1
```

### Step 2: Start the collector

```bash
mkdir -p /var/netflow/data
ip netns exec collector nfacctd -p /var/run/nfacctd.pid \
    -l 10.10.0.1 -P 4739 \
    -r /var/netflow/data \
    -t 300
```

The `-t 300` rotates the data file every 300 seconds (5 minutes — the standard nfdump cadence).

### Step 3: Run `code/main.py` against a synthetic IPFIX packet

The companion script simulates an exporter pushing one IPFIX packet with one Template Set (FlowSet ID 2) and one Data Set. It prints the parsed records in human-readable form and the per-flow accounting.

```bash
python3 code/main.py
```

Expected output (truncated):

```
=== IPFIX PARSER — synthetic single-packet export ===
[header] version=10 length=60 export_time=1748208000
          sequence=1 observation_domain=42

[flowset id=2 length=36]  TEMPLATE
  template_id=256 field_count=4
    [1]  IE 8  srcIPv4Address        (key)
    [2]  IE 12 dstIPv4Address        (key)
    [3]  IE 4  protocolIdentifier    (key)
    [4]  IE 7  sourceTransportPort   (key)
  scope_count=0

[flowset id=256 length=24]  DATA (template_id=256)
  record[1] src=10.10.1.2 dst=10.10.2.2 proto=6 sport=443
  record[2] src=10.10.2.2 dst=10.10.1.2 proto=6 sport=51234
...

=== ACCOUNTING — per-flow totals ===
TOP by octets:
  10.10.1.2 -> 10.10.2.2 proto=6 sp=443   pkts=1240  octets=1,716,840
  10.10.2.2 -> 10.10.1.2 proto=6 sp=51234 pkts=1198  octets=  144,360
```

### Step 4: Validate the live export with `tcpdump`

In a separate terminal:

```bash
ip netns exec exporter tcpdump -i veth-e-c -nn -c 5 port 4739
```

Now generate traffic from `h1` to `h2`:

```bash
ip netns exec h1 bash -c \
  'for i in $(seq 1 50); do
       curl --max-time 1 http://10.10.2.2:8080/ 2>/dev/null;
   done'
```

You should see five UDP/4739 packets with `version=10` (IPFIX) and the same `observation_domain=42` value. `nfcapd` writes a `.nfcap` file to `/var/netflow/data` every 300 seconds; force a flush with `kill -USR1 $(cat /var/run/nfacctd.pid)` to read immediately.

### Step 5: Read the captured data

```bash
nfdump -R /var/netflow/data -c 50 -o extended
```

You should see flow records matching the synthetic dataset from Step 3. If `nfdump` reports zero records, check `nfcapd`'s log file (`/var/log/nfdump.log` by default); the most common cause is a firewall on the collector blocking UDP/4739.

## Use It

| Capability | `code/main.py` (offline) | nfdump 1.7 / `nfcapd` | Cisco IOS `ip flow` / `sampled` |
|---|---|---|---|
| Parse NetFlow v5 fixed records | yes (subset) | yes | emits |
| Parse NetFlow v9 templates | yes | yes | emits |
| Parse IPFIX variable records | yes | yes | emits (since IOS-XE 17) |
| Per-flow octet accounting | yes | yes (`-s bytes`) | yes (via CLI/NetFlow collector) |
| Sampling math (RFC 5475 1-in-N) | yes | yes (`-s packet` with rate) | yes (`samplerate` option template) |
| Live UDP/4739 capture | no (offline) | yes | yes (exporter) |
| Bidirectional flow correlation | partial | yes (`-b`) | yes (BIF, RFC 5103) |
| Per-record raw byte hexdump | yes | yes (`-X`) | n/a |

## Ship It

The reusable artifact is the IPFIX template parser in `code/main.py`. Drop it into a toolchain to validate that any exporter is sending what you expect: feed it the raw bytes from `tcpdump -X port 4739`, and the script will tell you which Information Elements are present, in what order, and with what scope. Use it to catch a misconfigured router that suddenly drops IPv4 source addresses and switches to MPLS labels — the script flags the IE swap as a parser failure.

## Exercises

1. **Subnet the lab for IPv6.** Replace `10.10.x.x/30` with `fd00:10:10::/64` per link and re-emit IPFIX with IE 27 (`sourceIPv6Address`, 16 bytes) instead of IE 8. Confirm the parser correctly handles the doubled record size.
2. **Add sampling.** Set the exporter to 1-in-10 sampling (`nfacctd -S 10`), recompute the octet totals from the un-sampled data, and verify that observed values are within √N of the true value (the standard-error envelope for random sampling).
3. **Simulate a DDoS.** Generate 50 concurrent `curl` loops from `h1` to a single /32 on `h2`. After 5 minutes, run `nfdump -R /var/netflow/data -s dst/bytes` and identify the destination /32 — this is exactly the query that answers "who is being attacked".
4. **Add DSCP to the template.** Extend the IPFIX template to include IE 5 (`classOfServiceIPv4`) and re-export. Re-run the parser to confirm the DSCP byte round-trips through the binary protocol. This is how QoS-aware accounting is done.
5. **Detect template churn.** Send a corrupted template (`template_id=257` declared but no matching data) and verify the collector does not lock up. Add explicit handling in your parser for missing templates (RFC 7011 §6.1).
6. **Backwards compatibility.** Emit the same data as NetFlow v5 (fixed 7-record layout) and run the v5 decoder. Confirm octet counts agree to within the v5 quantization (RFC 3954 §2.3.1 notes v5 uses 32-bit counters; v9 uses 64-bit).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Flow | "A conversation on the network" | A unidirectional sequence of packets matching a key (typically 5-tuple) within an observation interval (RFC 5101 §3). |
| Template | "The schema of the flow record" | A field layout (sequence of IE IDs + lengths) declared once and referenced by Data Records (RFC 7011 §3.4). |
| Information Element | "A field in the flow" | An ID + length + semantic from the IANA IPFIX registry, e.g. IE 8 = `srcIPv4Address`, IE 4 = `protocolIdentifier`. |
| Observation Domain | "The exporter's ID" | A 32-bit ID distinguishing multiple exporters on the same collector (RFC 7011 §3.1). |
| Sampling rate | "How often we record" | 1-in-N packet or flow sampling; the inverse rate must be communicated to the collector via an Option Template (RFC 5475). |
| UDP/4739 | "The collector port" | IPFIX default port; v9 uses 9995, v5 uses 2055. UDP is deliberate — flow export tolerates loss better than reorder (RFC 7011 §10). |
| nfcapd | "Stores flow data" | The nfdump collector; rotates `.nfcap` files every `-t` seconds (default 300) for time-windowed queries. |
| Drop counter | "We lost flows" | `nfexp_drops` on the exporter; the first health metric to alarm on, before SNMP and before CPU. |

## Further Reading

- [RFC 3954](https://www.rfc-editor.org/rfc/rfc3954) — Cisco Systems NetFlow Services Export Version 9 (the format that made NetFlow extensible)
- [RFC 7011](https://www.rfc-editor.org/rfc/rfc7011) — IPFIX Protocol Specification (the IETF standardization of v9)
- [RFC 5101](https://www.rfc-editor.org/rfc/rfc5101) — Specification of the IPFIX File Writers (and bidirectional flows)
- [RFC 5103](https://www.rfc-editor.org/rfc/rfc5103) — Bidirectional Flow Export using IPFIX (BIF)
- [RFC 5475](https://www.rfc-editor.org/rfc/rfc5475) — Sampling and Filtering Techniques for IPFIX (PSAMP)
- [RFC 5474](https://www.rfc-editor.org/rfc/rfc5474) — Definition of PSAMP Information Elements
- [IANA IPFIX Information Elements](https://www.iana.org/assignments/ipfix/ipfix.xhtml) — the registry of IE IDs (your template must cite real IDs)
- [nfdump / nfcapd documentation](https://github.com/phaag/nfdump) — the open-source collector this lesson uses
- Trammell, "Improving NetFlow's Persistence" (ETH Zürich, 2019) — empirical study of what production networks actually export