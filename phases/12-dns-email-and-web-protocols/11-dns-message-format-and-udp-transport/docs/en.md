# DNS Message Format and UDP Transport

> DNS queries and responses ride in a single binary message defined by RFC 1034 and RFC 1035: a 12-byte fixed header (ID, flags, four 16-bit counters for QD/AN/NS/AR), then four sections that each carry resource records using a compact length-prefixed label format. The same wire format encodes both question and answer — the server reuses the header, copies the question section verbatim into the reply, and appends answer, authority, and additional records. By default the transport is UDP on port 53 with a 512-byte message limit (RFC 1035 §4.2.1); large responses, DNSSEC, and many modern operations flip on the EDNS(0) OPT pseudo-RR (RFC 6891) to advertise a larger UDP payload buffer and the DO bit (RFC 4033, RFC 8482) so a single UDP datagram can carry DNSSEC signatures. A 16-bit query ID lets a client correlate the response to one of many in-flight requests, and TCP fallback (RFC 7766) engages for truncated answers, zone transfers (AXFR), or any response that overflows the advertised UDP buffer.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Phase 11 (UDP), Phase 9 (IPv4/IPv6), the prior DNS lessons in Phase 12
**Time:** ~75 minutes

## Learning Objectives

- Parse a DNS message header by hand: ID, QR/Opcode/AA/TC/RD/RA/Z/AD/CD/RCODE flags, and the four section counts.
- Encode and decode a domain name as a sequence of length-prefixed labels, including the 0x00 root terminator and RFC 1035 message-compression pointers (`0xC0 | offset`).
- Build a complete question message for A, AAAA, MX, PTR, TXT, SRV, and NS queries, then decode the matching response and read its answer, authority, and additional sections.
- Explain the 512-byte UDP limit (RFC 1035) and how EDNS(0) OPT (RFC 6891) extends it without breaking compatibility with old resolvers.
- Distinguish the EDNS(0) DO bit (DNSSEC OK, RFC 4033) from the AD bit (Authenticated Data, RFC 3655) and know when each is set.
- Reason about when a stub resolver falls back from UDP to TCP (RFC 7766), including truncation, zone transfers, and large DNSSEC responses.

## The Problem

You run `dig +noedns @8.8.8.8 example.com A` and see a clean 12-byte header plus one question and one answer. You then run `dig @8.8.8.8 dnssec-failed.org A` and the same shape appears but with a pile of OPT and RRSIG records attached — yet the same UDP packet. You also remember a fact from the previous lesson: every DNS query is "supposed" to be UDP, but you have heard that big responses get truncated and clients retry over TCP. You want to see the wire format, not just the abstract notion of "a DNS packet", so you can read a `tcpdump` capture and a `dig +trace` output without translation.

The trap is treating DNS as a black box. The header is small, the section model is regular, and every record class (IN, CH, ANY) and type (A, NS, MX, …) flows through the same four sections. Once you can decode one record you can decode them all. The lesson ends with you parsing a real-format message in `code/main.py` so you can verify with `dig` what you computed.

## The Concept

### The 12-byte header, byte by byte

Every DNS message — query, response, AXFR, all of it — starts with a 12-byte fixed header defined in RFC 1035 §4.1.1. Multi-byte integers are big-endian (network byte order):

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0 | 2 | ID | Query identifier; copied by the server into the response so the client can match it |
| 2 | 1 | QR | 0 = query, 1 = response |
| 3 | 1 | Opcode | 0 = standard query, 1 = inverse query (obsolete), 2 = STATUS, 4 = NOTIFY, 5 = UPDATE |
| 4 | 1 | AA TC RD | AA = authoritative answer; TC = truncated; RD = recursion desired |
| 5 | 1 | RA Z AD CD RCODE | RA = recursion available; Z = reserved; AD = authenticated data (RFC 3655); CD = checking disabled; RCODE = response code |
| 6 | 2 | QDCOUNT | Number of entries in the question section |
| 8 | 2 | ANCOUNT | Number of entries in the answer section |
| 10 | 2 | NSCOUNT | Number of entries in the authority section |
| 12 | 2 | ARCOUNT | Number of entries in the additional section |

The bits in bytes 4 and 5 pack several 1-bit flags alongside multi-bit fields. RFC 1035 defines byte 4 as `AA|TC|RD` (1-bit each), and RFC 3655 later added the AD bit, while RFC 4033 codified the CD bit. The RCODE field (low 4 bits of byte 5) extends via EDNS(0) into an 8-bit extended RCODE in the OPT pseudo-record (RFC 6891).

RCODE values that matter in practice: 0 = NOERROR, 1 = FORMERR, 2 = SERVFAIL, 3 = NXDOMAIN, 4 = NOTIMP, 5 = REFUSED. Extended RCODE bits 4..7 are carried in OPT (RFC 6891) so DNSSEC errors such as 6 = DNSKEY missing or 16 = BADSIG still fit the wire format without breaking the old 4-bit field.

### Names on the wire: length-prefixed labels

A domain name is encoded as a sequence of labels, each label prefixed by a 1-byte length and terminated by a zero-length root label. `example.com` becomes `\x07example\x03com\x00`:

```
example.com.   =   07 65 78 61 6d 70 6c 65   03 63 6f 6d   00
                  ^- 7 bytes "example"   ^- 3 bytes "com"   ^- root (.)
```

RFC 1035 §4.1.4 also defines a **message-compression pointer**: if the high two bits of a length byte are `11`, the remaining 14 bits are an offset back into the message. A client reading a name sees `0xC0 | offset` (e.g. `0xC00C` = pointer to offset 12, the start of the question section) and jumps there, copying labels until it hits either another pointer or the terminating zero length. This is how an answer section can re-use the QNAME without retransmitting it: the response says "the owner name is the same one as the question".

### The four sections, in order

A query contains only the question section (QDCOUNT=1, the others zero). A response reuses the same header, echoes the question verbatim, then appends three more sections:

- **Answer (AN)** — RRs that answer the question (e.g., the A record for the QNAME).
- **Authority (NS)** — RRs that point toward the authoritative server (typically NS records; for negative answers, the SOA of the relevant zone, RFC 2308).
- **Additional (AR)** — RRs that the server helpfully adds to save round trips (e.g., the A record for an NS hostname, or the OPT record advertising EDNS).

Each RR (RFC 1035 §3.2.1) is: name (labels or compression pointer), TYPE (2 bytes), CLASS (2 bytes, `IN = 1` for Internet), TTL (4 bytes, seconds), RDLENGTH (2 bytes), RDATA (RDLENGTH bytes). TTL is the cache lifetime, not a session timer. TTL=0 means "do not cache", and TTL values are 32-bit unsigned integers even though many tools display them as durations.

### Worked decode: a single A query and response

Hex dump (with spaces for readability, two-octet groups aligned to byte offsets; this is one realistic capture):

```
00 00          ID = 0x0001 (client chose 1)
01 00          QR=0  Opcode=0  AA=0  TC=0  RD=1  RA=0  Z=0  AD=0  CD=0  RCODE=0
00 01          QDCOUNT = 1
00 00          ANCOUNT = 0
00 00          NSCOUNT = 0
00 00          ARCOUNT = 0
07 65 78 61 6d 70 6c 65 03 63 6f 6d 00    QNAME: example.com
00 01          QTYPE = A
00 01          QCLASS = IN
```

That is exactly 12 + 17 = 29 bytes. The server replies with the same header bytes 0..1 copied, QR=1, RA=1 (because Google's resolver performs recursion), ANCOUNT=1, and the answer section: pointer `\xc0\x0c` to offset 12 (the question name), TYPE=1, CLASS=1, TTL=300 (5 minutes), RDLENGTH=4, RDATA = the four-byte IPv4 address.

### UDP, and the 512-byte limit

RFC 1035 §4.2.1 mandates that DNS messages carried over UDP fit in a single datagram and that any message whose size would exceed 512 bytes must be truncated with TC=1. The stub then retries over TCP (RFC 7766). This made sense on 1980s MTUs but is painful for DNSSEC: a signed `.org` answer with several RRSIGs easily exceeds 512 bytes.

EDNS(0) (RFC 6891) solves this without changing the header. The client adds an OPT pseudo-record (TYPE=41) to the additional section of its query, advertising a UDP payload buffer (commonly 4096 or 1232 bytes — 1232 fits safely in the IPv6 minimum MTU of 1280 minus IPv6 + UDP headers, RFC 6891 §6.2.5) and the version=0. If the server understands EDNS, it obeys the advertised buffer; if not, it ignores OPT and falls back to the 512-byte limit. EDNS(0) also carries the **DO bit** (DNSSEC OK, RFC 4033) — when set, the client is asking the server to include DNSSEC records (DNSKEY, RRSIG, DS, NSEC, NSEC3) in the response — and the **AD bit** (Authenticated Data, RFC 3655), which the server sets in the response header when it has cryptographically validated every record in the answer.

### Recursion, TTLs, and the 16-bit correlation ID

The ID field is the only correlation token. The resolver library picks a fresh ID per outstanding query, sends the request, and stores `(ID, query_state)` so when the response arrives it can match ID-for-ID. UDP does not guarantee delivery and does not give you "port 53 response to my request", so the ID plus the source port (the client picks an ephemeral port; the server replies from 53) is the entire correlation. RFC 5452 mandates that the ID and source port together have enough entropy to resist blind forgery — at least 122 bits in modern guidance.

A TTL is the number of seconds a record may be cached. The TTL on a CNAME chain is honored independently at each hop — the A record's TTL controls the cache lifetime of the A, the CNAME's TTL controls the CNAME. When a zone signs its records with DNSSEC, the RRSIG record has its own "signature inception / expiration" timestamps that are unrelated to the TTL; those are checked cryptographically, not used for caching.

## Build It

1. Skim `code/main.py` and run it. It should print a parsed header, the encoded name, a wire-format query, and the byte/byte decode of a captured response.
2. Verify the 512-byte UDP limit for yourself: `dig @8.8.8.8 isc.org ANY` and compare to `dig @8.8.8.8 isc.org A` — the ANY query returns the OPT record advertising the buffer.
3. Capture a single query/response pair with `tcpdump -ni any -w dns.pcap udp port 53` while running `dig +noedns @127.0.0.1 example.com A` against a local resolver. Open in Wireshark, expand "Domain Name System", and confirm the fields.
4. In `code/main.py`, change `build_query` to ask for `AAAA` and re-run; the only difference is QTYPE=28 instead of 1.
5. Toggle `use_edns = True` to add an OPT record and observe how the response payload can grow beyond 512 bytes.

```python
# Excerpt from code/main.py — header pack/unpack
def pack_header(qr: int, opcode: int, aa: int, tc: int, rd: int,
                ra: int, ad: int, cd: int, rcode: int,
                qd: int, an: int, ns: int, ar: int) -> bytes:
    flags = ((qr & 1) << 15) | ((opcode & 0xF) << 11) | ((aa & 1) << 10) | \
            ((tc & 1) << 9) | ((rd & 1) << 8) | ((ra & 1) << 7) | \
            ((z & 1) << 6) | ((ad & 1) << 5) | ((cd & 1) << 4) | (rcode & 0xF)
    return struct.pack("!HHHHHH", qid, flags, qd, an, ns, ar)
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Header encode/decode | `pack_header`, `unpack_header` | `dnspython`'s `dns.message.make_response` | RFC 1035 §4.1.1 |
| Name encoding | `encode_name` (length-prefix + compression) | `dns.name.Name.to_wire()` | RFC 1035 §4.1.4 |
| Record parsing | `decode_rr` | `dns.rdata.from_wire` | RFC 1035 §3.2.1 |
| EDNS(0) OPT | `build_opt_record` | `dns.edns` | RFC 6891 |
| DNSSEC OK flag | `DO=1` in OPT flags | `dig +dnssec` | RFC 4033, RFC 8482 |
| TCP fallback | `send_tcp_query` | `getaddrinfo` with TCP fallback | RFC 7766 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A reference decoder for DNS messages captured with `tcpdump -w`. The decoder takes a hex dump or a `pcap` reader output and prints each RR in human-readable form, including compressed-name pointers.
- A "transport selector" that picks UDP vs TCP for a given scenario (small query → UDP, >512-byte DNSSEC → TCP with RFC 7766 retry).
- A worked table comparing the same query with and without EDNS(0) so a teammate can see exactly what OPT changes.

Start from [`outputs/prompt-dns-message-format-and-udp-transport.md`](../outputs/prompt-dns-message-format-and-udp-transport.md).

## Exercises

1. Manually encode the query `dig +noedns @127.0.0.1 cs.example.edu MX`. Predict each byte of the header and the QNAME/QTYPE/QCLASS; verify with `code/main.py`.
2. Capture a DNS response with `tcpdump -w out.pcap udp port 53` and decode it with the `Message` class. Verify the compression pointer by following `\xC0\x0C` back to the QNAME.
3. Run `dig +dnssec @8.8.8.8 dnssec-failed.org A` and identify the OPT pseudo-record, the DO/AD bits, and the RRSIG in the answer section.
4. Set a client UDP buffer of 1232 in EDNS(0) and compare a query to the same name without EDNS — does the server still cap responses at 512 when OPT is absent?
5. Force a truncated response (use a name whose ANY answer exceeds the buffer) and observe the resolver falling back to TCP with RFC 7766.
6. Build a 512-byte packet in raw bytes, set TC=1, and have `code/main.py` tell you which section the truncation cuts off.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Header | "the 12-byte header" | Fixed RFC 1035 prefix: ID, flags, and the four 16-bit section counts |
| QNAME | "the name being asked" | Length-prefixed label sequence ending in `\x00` (the root label) |
| Compression pointer | "that 0xC0 trick" | High two bits `11` plus 14-bit offset; jumps back into the same message |
| OPT record | "EDNS0" | A pseudo-RR (TYPE=41) in the additional section that advertises buffer, flags, and extended RCODE |
| DO bit | "DNSSEC OK" | RFC 4033 flag in OPT asking the server to include DNSSEC records |
| AD bit | "Authenticated Data" | RFC 3655 header flag set when the server has validated all answers cryptographically |
| TC bit | "truncated" | RFC 1035 header flag set when the response was cut to fit the UDP buffer; client retries over TCP |
| RCODE | "response code" | Low 4 bits of byte 5; 0..5 defined by RFC 1035, extended to 8 bits via OPT (RFC 6891) |

## Further Reading

- RFC 1034 — Domain Names — Concepts and Facilities
- RFC 1035 — Domain Names — Implementation and Specification (header, label format, UDP/TCP transport)
- RFC 6891 — Extension Mechanisms for DNS (EDNS(0))
- RFC 7766 — DNS Transport over TCP — Implementation Requirements
- RFC 4033 — DNS Security Introduction and Requirements (DO bit)
- RFC 8482 — Clearing the DNS Flag bits in the DNSKEY RR
- RFC 3655 — REDIRECT (AD/CD header bits)
- RFC 5452 — Measures for Making DNS More Resilient against Forged Answers
- Wireshark Display Filters: `dns`, `dns.flags.response`, `dns.flags.authoritative`, `dns.flags.truncated`, `dns.flags.recursiondesired`
- `dig` quick reference: `+noedns`, `+dnssec`, `+bufsize=4096`, `+tcp`, `+trace`
