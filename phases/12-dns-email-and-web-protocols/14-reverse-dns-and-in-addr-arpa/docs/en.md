# Reverse DNS and in-addr.arpa Lookups

> Forward DNS maps names to addresses; reverse DNS maps addresses back to names, and the mechanism is the `in-addr.arpa` (IPv4) and `ip6.arpa` (IPv6) special-use domains defined in RFC 1035 and RFC 3596. To look up `192.0.2.10`, a resolver constructs the name `10.2.0.192.in-addr.arpa.` (note the byte-reversal) and queries it for the PTR record type. The matching record typically looks like `10 IN PTR mail.example.com.`. This seemingly backwards convention lets reverse lookups ride on the same hierarchical delegation machinery as forward lookups: a /16 of IPv4 space delegated to an organization becomes a /16 of `in-addr.arpa` delegated to that organization, served by its own NS set with glue. Reverse DNS is famously required by mail servers (RFC 5321 §5.1) — many MTAs refuse SMTP connections from IPs that lack a valid PTR record because spammers usually cannot arrange one. IPv6 reverses use the nibble-reversed domain `ip6.arpa` (RFC 3596), and a `/128` reverse zone is a single PTR in a deeply-nested domain.

**Type:** Build
**Languages:** Python, shell
**Prerequisites:** Phase 12 lessons on DNS records, recursion, and zone files
**Time:** ~75 minutes

## Learning Objectives

- Construct a reverse name for an IPv4 and IPv6 address by reversing the byte or nibble order and appending `in-addr.arpa.` or `ip6.arpa.`.
- Build a minimal reverse zone file with a SOA, NS, and PTR records, and verify the corresponding forward zone matches.
- Use `dig -x` to perform a reverse lookup and read the returned PTR record, including the matching forward A/AAAA.
- Explain why mail servers (RFC 5321 §5.1) and many abuse-prevention pipelines refuse connections from IPs without valid PTR records.
- Author an IPv6 reverse zone from a /64 prefix and identify the matching `ip6.arpa` delegation path.

## The Problem

You set up a mail server on `203.0.113.5`. It can send mail to some recipients but bounces with errors like `554 ... ... does not designate 203.0.113.5 as permitted sender` or `450 ... reverse DNS lookup failed`. Other recipients accept it. The pattern is consistent: large providers reject or score the message based on the absence of a PTR record. The hostname `mail.example.com` resolves forward to `203.0.113.5`, but `5.113.0.203.in-addr.arpa` does not resolve back to any name. You need to understand why this asymmetry exists, how to set up a PTR record properly, and how to verify it is correctly delegated.

The trap is treating reverse DNS as "the inverse of forward DNS". It is not. Forward DNS uses the ordinary DNS hierarchy (delegations are inherited top-down), while reverse DNS uses a separate artificial hierarchy (`.in-addr.arpa`) with its own delegations. You can have a working forward zone and no reverse zone at all — the two are independent. Reverse delegations are usually managed by the IP address allocator (your ISP, your cloud provider, or the RIRs) and you must request them explicitly.

## The Concept

### Byte-reversal: the convention that makes reverse DNS work

Forward DNS is hierarchical from the right. `mail.example.com.` is `com → example → mail`. To make reverse DNS work the same way, the bytes of the IP address are reversed and `in-addr.arpa.` is appended:

| IPv4 | Reversed octets | in-addr.arpa name | PTR record |
|---|---|---|---|
| 192.0.2.10 | 10.2.0.192 | `10.2.0.192.in-addr.arpa.` | `10 IN PTR mail.example.com.` |
| 198.51.100.7 | 7.100.51.198 | `7.100.51.198.in-addr.arpa.` | `7 IN PTR ns1.example.com.` |
| 203.0.113.42 | 42.113.0.203 | `42.113.0.203.in-addr.arpa.` | `42 IN PTR web.example.com.` |

The byte-reversal keeps the most-significant bytes at the bottom of the name (closest to the root), just like in the forward tree. A /16 network like `192.0.2.0/24` becomes a /24 of `2.0.192.in-addr.arpa`, owned by whoever owns the `2.0.192` delegation.

### The `in-addr.arpa.` tree

The special-use domain `in-addr.arpa.` was allocated by RFC 1035. ARIN, RIPE NCC, APNIC, and the other RIRs own the top of it; each RIR delegates chunks downward to its member ISPs, which delegate chunks downward to their customers. An organization that wants authoritative PTR records for its allocated /24 must:

1. Be assigned the /24 (or a larger block) by an RIR or upstream ISP.
2. Ask the upstream to create NS records at `0.2.192.in-addr.arpa.` (or whatever) pointing at the organization's authoritative name servers.
3. Publish the PTR records in a zone file served by those name servers.

If the upstream never delegates the reverse zone, the organization cannot authoritatively publish PTR records. They can ask nicely, configure their servers to also be authoritative via the `master`/`slave` config of the upstream, or move to a provider that delegates by default.

### IPv6 reverse: nibble-reversal and `ip6.arpa`

RFC 3596 allocates `ip6.arpa.` for IPv6 reverse. The convention is to reverse the *nibbles* (4-bit half-bytes) of the address, not the bytes, and append `ip6.arpa.`. For `2001:db8::1`, the reverse name is built by expanding the address to its full 32-nibble form (`2001:0db8:0000:0000:0000:0000:0000:0001`), reversing those nibbles, and inserting dots between every nibble:

```
2001:0db8:0000:0000:0000:0000:0000:0001
nibbles:    2 0 0 1  0 d b 8  0 0 0 0  0 0 0 0  0 0 0 0  0 0 0 0  0 0 0 0  0 0 0 1
reversed:   1 0 0 0  0 0 0 0  0 0 0 0  0 0 0 0  0 0 0 0  0 0 0 0  8 b d 0  1 0 0 2
name:       1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa.
```

The `/128` reverse zone for this address is a single PTR record at that name. Most operators only delegate `/64` reverse zones, which means 16 nibbles of the `ip6.arpa` tree, or even shorter delegations. The DNS lookups for IPv6 reverses are deeply nested: a `/128` lookup traverses 64 labels to reach the leaf.

### Why mail servers care (RFC 5321 §5.1)

SMTP's opening handshake reveals the sending MTA's IP via the TCP source address. RFC 5321 §5.1 says the receiving MTA "SHOULD reject" or otherwise flag messages when the reverse lookup fails or the forward confirmation does not match. The most common policy is:

1. Look up the sending IP via reverse DNS (PTR).
2. Look up the resulting name via forward DNS (A or AAAA).
3. Confirm that one of the forward A/AAAA addresses matches the original sending IP.

This is the **forward-confirmed reverse DNS** (FCrDNS) check. Spam sources usually fail one of the steps. Legitimate operators can publish PTR records matching their forward DNS, and FCrDNS succeeds. RFC 7003 (BATV-style) and RFC 7208 (SPF) complement this by encoding the sending policy directly in DNS.

### The deliverability triangle

A mail server that wants to deliver to Gmail, Outlook, Yahoo, and the major EU providers must have:

- A forward A (and ideally AAAA) record for the sending hostname.
- A matching PTR record for the sending IP that resolves to that hostname.
- An SPF (RFC 7208) record that authorizes the IP to send for the domain.
- A DKIM (RFC 6376) signature on outbound messages.
- A DMARC (RFC 7489) record at `_dmarc.example.com` saying what to do with failures.

PTR is the cheapest to set up and the most often missed.

### Forward/reverse mismatch is a feature, not a bug

A common confusion: why does my reverse record point to a different name than the forward one resolves to? Both are valid as long as one direction's reverse FCrDNS loop closes. Most operators set the PTR to the canonical hostname (the one an `A` query returns) so that both forward and reverse reach the same name. But there is no protocol requirement that they match — RFC 1035 treats PTR records as independent of any A record. The match is a convention enforced by recipients, not by DNS itself.

## Build It

1. Run `code/main.py` to convert addresses to reverse names, build a tiny reverse zone, and run the FCrDNS loop.
2. Build your own reverse zone file for `203.0.113.0/24`. Use a `$ORIGIN 0.113.0.203.in-addr.arpa.` directive and PTR records for each host you want to map back to a name.
3. Validate with `named-checkzone 0.113.0.203.in-addr.arpa zone/db.203.0.113`.
4. Verify the loop with `dig -x 203.0.113.5 @your-server` (should return the PTR you set) and then `dig your-returned-name A` (should return `203.0.113.5` again — FCrDNS closed).
5. Test IPv6 reverse: convert `2001:db8::1` and verify `dig -x 2001:db8::1` returns the PTR you set in `ip6.arpa`.

```python
# Excerpt from code/main.py
def ipv4_to_arpa(ip: str) -> str:
    octets = ip.split(".")
    return ".".join(reversed(octets)) + ".in-addr.arpa."
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| IPv4 reverse name | `ipv4_to_arpa` | `dig -x` | RFC 1035 |
| IPv6 reverse name | `ipv6_to_ip6_arpa` | `dig -x` | RFC 3596 |
| Reverse zone file | `render_zone(origin, ptrs)` | `named-checkzone` | RFC 1035 §5 |
| FCrDNS check | `forward_confirmed(ip, ptr, a)` | `pyspf`, `policyd-spf` | RFC 5321 §5.1 |
| Reverse delegation | (manual at ISP portal) | ARIN, RIPE, APNIC portals | RFC 6996 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `zone/db.203.0.113` template with the SOA, NS, and PTR records needed for a delegation, plus the matching forward zone.
- A pre-deliverability checklist that walks FCrDNS, SPF, DKIM, and DMARC and flags which is missing.
- A short shell script that runs `dig -x` for each of your outbound mail servers and reports the resolved name vs the canonical forward name.

Start from [`outputs/prompt-reverse-dns-and-in-addr-arpa.md`](../outputs/prompt-reverse-dns-and-in-addr-arpa.md).

## Exercises

1. Convert `192.0.2.10`, `198.51.100.7`, and `203.0.113.42` to their `in-addr.arpa` names. Verify each with `dig -x`.
2. Build a /24 reverse zone for `203.0.113.0/24` containing PTR records for at least three hosts. Validate with `named-checkzone`.
3. Set up an IPv6 reverse delegation: convert `2001:db8:1234:5678::1` to its `ip6.arpa` name and author the matching PTR.
4. Run an FCrDNS check against your mail server's IP. Confirm that the loop closes: PTR → name → A → same IP.
5. Read RFC 5321 §5.1 and identify the exact language the spec uses for the PTR-policy SHOULD. Is it a MUST anywhere?
6. Build a tiny `policyd-spf` or `pyspf` configuration that uses your PTR record as one of the allowed-sender checks.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Reverse DNS | "the opposite of DNS" | Mapping IP addresses to names via the `in-addr.arpa` (IPv4) and `ip6.arpa` (IPv6) trees |
| in-addr.arpa | "the reverse zone" | RFC 1035 special-use domain that hosts IPv4 PTR records |
| ip6.arpa | "the IPv6 reverse zone" | RFC 3596 special-use domain that hosts IPv6 PTR records (nibble-reversed) |
| PTR record | "the reverse record" | A DNS RR that maps a reversed IP name to a hostname |
| FCrDNS | "forward-confirmed reverse DNS" | PTR(name) → A → same IP loop; used as a sender-reputation signal |
| Byte reversal | "the backwards order" | Octets of an IPv4 address reversed before appending `in-addr.arpa` |
| Nibble reversal | "the IPv6 backwards order" | 4-bit half-bytes of an IPv6 address reversed before appending `ip6.arpa` |
| Reverse delegation | "the /24 of in-addr" | An RIR/ISP granting an organization authoritative control over a chunk of `in-addr.arpa` |

## Further Reading

- RFC 1035 §3.3.12 — PTR record format
- RFC 3596 — DNS Extensions to Support IPv6 (`ip6.arpa`, AAAA record)
- RFC 5321 §5.1 — SMTP receiving-server semantics and PTR policy
- RFC 5855 — Common Errors in DNS Reverse Mappings
- RFC 6996 — Autonomous System to DNS RR Mapping (related, for AS lookup)
- RFC 7208 — Sender Policy Framework (SPF) — complements FCrDNS as a sending-policy signal
- RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC)
- `dig -x` reference — performs the PTR query for an address
- ARIN / RIPE / APNIC reverse delegation portals
