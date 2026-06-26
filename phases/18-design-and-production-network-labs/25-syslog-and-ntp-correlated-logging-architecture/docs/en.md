# Syslog and NTP correlated logging architecture

> At 03:42 UTC you receive three alerts within 90 seconds: "router1 BFD session down", "router1 OSPF neighbor down", "router2 BGP holdtimer expired". Each alert cites a different timestamp: `Mar 14 03:42:01`, `03:42:01.214`, `03:42:01.612`. But the timestamps are wrong — router2's clock is 700 ms ahead of router1's, and the SIEM is ordering the events in arrival order, not causal order. The root-cause analysis fails because you cannot prove which failure triggered which. The fix is **NTP (RFC 5905) synchronization to ≤ 10 ms skew across the fleet** and **structured syslog (RFC 5424) with a millisecond-precision timestamp** so the SIEM can correlate causally. This lesson builds a 4-node logging architecture (`syslog-server`, `router1`, `router2`, `client`), configures `rsyslog` (the de facto Linux syslog, RFC 5424) on each host to relay over TLS, runs `chrony` to synchronize every host to the server with sub-millisecond accuracy, and uses the companion `code/main.py` to parse a stream of RFC 5424 syslog messages and reorder them by causal timestamp. The end state: the SIEM now sees `router2` BGP fail *before* router1's OSPF — the true causal order.

**Type:** Build
**Languages:** Python, shell, rsyslog, chrony
**Prerequisites:** Phase 09 IPv4 basics, ability to run `systemd` services, comfort with `journalctl`
**Time:** ~75 minutes

## Learning Objectives

- Build a 4-node lab (`syslog-server`, `router1`, `router2`, `client`) with Linux network namespaces and connect them on `10.60.0.0/24` and `10.60.1.0/24`.
- Configure `rsyslog` (the de facto Linux syslog, RFC 5424) on `router1`/`router2` to relay messages over **RELP** (Reliable Event Logging Protocol, RFC 3195) or **TLS syslog** (RFC 5425) to `syslog-server:601`.
- Set up `chrony` (the modern NTP client, RFC 5905) with the server as the reference clock, and measure inter-host clock skew with `chronyc tracking` and `ntpdate -q`.
- Use `code/main.py` to parse an RFC 5424 syslog message (PRI, version, timestamp with sub-second precision, hostname, app-name, structured data, message), and reorder a stream of out-of-order events by their timestamps.
- Recognize the **RFC 5424 PRI** range (`<13>` facility `local0` severity `notice`) versus the legacy RFC 3164 BSD-syslog `PRI` (`<13>` = facility 1, severity 5).
- Distinguish **NTP stratum** (server is stratum 1, peers are stratum 2), **time-source** (GPS, PTP, atomic clock), and **clock skew** — the metric `chronyc tracking` reports as `System time : +0.000123456 seconds fast of NTP time`.

## The Problem

The first rule of incident response is "the timestamp you have is wrong". A router whose clock drifted 5 seconds overnight will produce log lines that look like they happened 5 seconds before they did. SIEMs that sort by arrival time or by per-host time create a paradox: the same event has two timestamps (host clock vs SIEM clock), and they disagree by seconds.

The fix is two-fold: (1) synchronize every host's clock to a common reference (NTP / chrony / PTP), and (2) use a syslog format that carries the synchronized timestamp on the wire — RFC 5424's `TIMESTAMP` field with millisecond precision and a `TIME-SECURED` SD-element when the message was digitally signed.

The trap is that **NTP is not installed by default** on most VM images and **chrony drift accumulates silently** — the first indication of trouble is the SIEM alerting on the gap. Production fleets run `chronyc tracking` daily and alert on `System time : > 0.001 seconds fast/slow`.

## The Concept

### Syslog RFC 3164 vs RFC 5424

The original syslog protocol (RFC 3164, 2001) carried a single-line message:

```
<PRI>TIMESTAMP HOSTNAME MSG TAG[PID]: MESSAGE
```

Example: `<189>Oct 11 22:14:15 router1 ospf[1234]: Neighbor 10.0.0.2 dead`.

Problems: no structured fields, no timezone information (assumed UTC but ambiguous), no reliable transport, no authentication, year missing.

RFC 5424 (2009) replaced it with a structured format:

```
<PRI>1 TIMESTAMP HOSTNAME APPNAME PROCID MSGID SD MSG
```

Example: `<165>1 2024-03-14T03:42:01.612Z router2 bgpd 1915 - - BGP holdtimer expired`. The `1` after `<PRI>` is the version (always 1). The timestamp is RFC 3339 / ISO 8601 with millisecond precision and explicit timezone. SD is a sequence of `SD-ELEMENT` (`[example@32473 iut="3" eventSource="Application" eventID="1011"]`).

### PRI = facility × 8 + severity

The PRI byte (RFC 5424 §6.2.1) encodes facility and severity:

- Facility: 0=kernel, 1=user, 2=mail, 3=daemon, 4=auth, 5=syslog, 6=lpr, 7=news, 8=uucp, 9=cron, 10=authpriv, 11=ftp, 16=local0..23=local7.
- Severity: 0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug.

PRI `<165>` = 165 = 20 × 8 + 5 = facility `local4`, severity `notice`. The PRI is always `<` and `>` around the number — printers extract it before the message hits the file or SIEM.

### Transport — UDP, RELP, or TLS

The default syslog transport is **UDP/514** (RFC 5426) — best-effort, lossy, no authentication. Suitable for LAN syslog relays where loss is acceptable. **RELP** (RFC 3195) adds TCP for reliability and replay-on-receiver-restart — used by `rsyslog`'s `omrelp` module. **TLS syslog** (RFC 5425) wraps the TCP session in TLS with mutual auth — required when syslog leaves the trusted network. Each `rsyslog` action line specifies the transport:

```
action(type="omfwd" target="10.60.0.1" port="601" protocol="tcp")
action(type="omrelp" target="10.60.0.1" port="20514")
action(type="omfwd" target="log.example.com" port="6514" StreamDriver="gtls")
```

### NTP / chrony in 90 seconds

NTP (Network Time Protocol, RFC 5905) synchronizes clocks over UDP/123 in a **stratum hierarchy**: stratum 0 is a hardware clock (GPS, atomic), stratum 1 is a server directly connected to one, stratum 2 is a server synchronized to a stratum 1, etc. The accuracy at each hop is bounded by the round-trip delay to the upstream.

`chrony` is the modern Linux NTP client (replacing `ntpd`). It runs two daemons: `chronyd` (the daemon) and `chronyc` (the CLI). On the server:

```bash
chronyd -q 'server 127.0.0.1 iburst' 'local stratum 1' 'allow 10.60.0.0/16'
```

On each client:

```bash
chronyd -q 'server 10.60.0.1 iburst maxpoll 4' 'makestep 1.0 3'
```

`makestep 1.0 3` allows the initial three updates to step the clock (instead of slewing) when the offset exceeds 1 second — the standard way to bring a fresh VM into sync.

### Why PTP for finance but NTP for everyone

Precision Time Protocol (PTP, IEEE 1588) achieves sub-microsecond accuracy by timestamping at the hardware NIC and using a separate timing network. It's what stock exchanges and cellular base stations use. NTP achieves millisecond accuracy over the existing data network. For SIEM correlation, NTP with sub-ms skew is sufficient; for HFT or 5G, you need PTP.

### Structured data — the SIEM's real friend

The SD field in RFC 5424 carries typed parameters as `SD-ELEMENT` pairs of `name=value`. Example:

```
[origin@32473 software="rsyslogd" version="8.2402.0"]
[timestamp@32473 fractionalSeconds="612"]
[event@32473 category="routing" subCategory="bgp" eventID="holdtimer"]
```

SIEM rules key on these SD-elements rather than regex on the message body — a 10x improvement in correlation accuracy.

## Build It

### Step 1: Build the 4-node lab

```bash
for n in syslog-server router1 router2 client; do ip netns add $n; done

ip link add veth-s-r1 type veth peer name veth-r1-s
ip link set veth-s-r1 netns syslog-server
ip link set veth-r1-s netns router1
ip netns exec syslog-server ip addr add 10.60.0.1/24 dev veth-s-r1
ip netns exec syslog-server ip link set veth-s-r1 up
ip netns exec router1 ip addr add 10.60.0.10/24 dev veth-r1-s
ip netns exec router1 ip link set veth-r1-s up

ip link add veth-s-r2 type veth peer name veth-r2-s
ip link set veth-s-r2 netns syslog-server
ip link set veth-r2-s netns router2
ip netns exec syslog-server ip addr add 10.60.0.11/24 dev veth-s-r2
ip netns exec syslog-server ip link set veth-s-r2 up
ip netns exec router2 ip addr add 10.60.0.20/24 dev veth-r2-s
ip netns exec router2 ip link set veth-r2-s up

ip link add veth-s-c type veth peer name veth-c-s
ip link set veth-s-c netns syslog-server
ip link set veth-c-s netns client
ip netns exec syslog-server ip addr add 10.60.0.30/24 dev veth-s-c
ip netns exec syslog-server ip link set veth-s-c up
ip netns exec client ip addr add 10.60.0.40/24 dev veth-c-s
ip netns exec client ip link set veth-c-s up
```

### Step 2: Install chrony on the server

```bash
ip netns exec syslog-server bash - <<'EOF'
apt-get update && apt-get install -y chrony rsyslog
cat > /etc/chrony/chrony.conf <<CFG
server 127.0.0.1 iburst
local stratum 1
allow 10.60.0.0/24
makestep 1.0 3
rtcsync
log measurements statistics tracking
CMD
chronyd -f /etc/chrony/chrony.conf
EOF
```

### Step 3: Configure the clients

```bash
for ns in router1 router2 client; do
  ip netns exec $ns bash - <<EOF
  apt-get install -y chrony rsyslog
  cat > /etc/chrony/chrony.conf <<CFG
  server 10.60.0.1 iburst maxpoll 4
  makestep 1.0 3
  rtcsync
  CMD
  chronyd -f /etc/chrony/chrony.conf
EOF
done
```

### Step 4: Verify clock sync

```bash
for ns in router1 router2 client; do
  ip netns exec $ns chronyc tracking | grep "System time"
done
```

All three should report `< 0.001 seconds` of drift within 30 seconds. If drift is larger, increase `iburst` to `iburst minpoll 4 maxpoll 4` to force more frequent polling.

### Step 5: Configure rsyslog to relay

```bash
ip netns exec router1 bash - <<'EOF'
cat > /etc/rsyslog.d/10-relay.conf <<CFG
*.* action(type="omfwd"
           target="10.60.0.1"
           port="601"
           protocol="tcp"
           Template="RSYSLOG_SyslogProtocol23Format")
CMD
rsyslogd
EOF
```

On the server, listen on TCP/601:

```bash
ip netns exec syslog-server bash - <<'EOF'
cat > /etc/rsyslog.d/10-server.conf <<CFG
module(load="imtcp")
input(type="imtcp" port="601")
template(name="RFC5424" type="string"
         string="%timegenerated:::date-rfc3339% %HOSTNAME% %syslogtag%%msg%\n")
action(type="omfile" template="RFC5424" file="/var/log/remote.log")
CMD
rsyslogd
EOF
```

### Step 6: Generate correlated events

```bash
ip netns exec router1 logger -p local4.notice "OSPF neighbor 10.60.0.10 dead"
ip netns exec router2 logger -p local4.notice "BGP holdtimer expired"
ip netns exec client  logger -p local4.notice "DNS lookup failed"
```

### Step 7: Run the parser to reorder by timestamp

```bash
python3 code/main.py /var/log/remote.log
```

Expected output:

```
=== RFC 5424 PARSER + CAUSAL REORDER ===
  raw line: <165>1 2024-03-14T03:42:01.612Z router2 bgpd 1915 - - BGP holdtimer expired
  pri=165  facility=local4  severity=notice
  ts=2024-03-14T03:42:01.612000Z  host=router2  app=bgpd  procid=1915
  msg=BGP holdtimer expired

CAUSAL ORDER (sorted by synchronized timestamp):
  2024-03-14T03:42:01.612Z router2 BGP holdtimer expired
  2024-03-14T03:42:01.815Z router1 OSPF neighbor 10.60.0.10 dead
  2024-03-14T03:42:02.001Z client  DNS lookup failed
```

This is the true causal order. Without NTP sync, the same log file would have shown the events in network-arrival order — which can be hours off if router1's clock is ahead.

## Use It

| Capability | `code/main.py` (parser) | rsyslog 8.x | syslog-ng | Splunk / Elastic ingest |
|---|---|---|---|---|
| RFC 5424 parser | yes | yes | yes | yes |
| RFC 3164 fallback parser | yes | yes | yes | yes |
| Timestamp normalization to UTC | yes | yes | yes | yes |
| Causal reorder | yes | n/a (rsyslog writes in arrival order) | n/a | yes (with synced hosts) |
| SD-element parsing | yes | yes | yes | yes |
| TLS transport | n/a (offline) | yes (`gtls` driver) | yes | yes (Splunk HEC) |
| RELP replay | n/a | yes (`omrelp`) | no | n/a |
| Chrony / NTP | n/a | n/a | n/a | n/a |

## Ship It

The reusable artifact is the RFC 5424 parser and causal reorder engine in `code/main.py`. Drop it into a log shipper, an alert triage tool, or a SIEM preprocessor to canonicalize incoming syslog. The same code path is what production triage tools use: parse, extract timestamp, normalize to UTC microseconds, sort, then group. With NTP-synced hosts the sort gives you causal order; without sync, it gives you a misleading chronology.

## Exercises

1. **Force a clock skew.** Set `router2`'s clock 5 seconds ahead with `date -s "+5 seconds"`, send 5 events from `router2`, and confirm the parser still places them after `router1`'s events because `router1`'s time is the synchronized reference.
2. **Add RELP.** Replace the TCP/601 with RELP/20514 (`omrelp`) and confirm logs survive a `kill -9` of the server — RELP replays buffered messages on restart.
3. **Add structured data.** Modify `logger -p local4.notice` to include an SD-ELEMENT (`logger -t bgpd[1915] -p local4.notice "..."`) and confirm the parser extracts `appname=bgpd`, `procid=1915`.
4. **Cross-check NTP.** Use `ntpdate -q 10.60.0.1` to query the server and compare to `chronyc tracking` — both should agree to within 10 ms.
5. **Force a leap second.** Use `chronyc -a 'burst 4/4'` to slew the clock fast, and observe the server's tracking stats change.
6. **Build an NTP stratum graph.** Use `chronyc sources -v` and `chronyc tracking` to draw a graph of which hosts synchronize to which servers.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Syslog | "Server logs" | The logging protocol (RFC 5424) — a structured UDP/TCP/TLS message format with PRI, timestamp, hostname, SD-elements, MSG. |
| PRI | "The priority" | 8-bit value = facility × 8 + severity (RFC 5424 §6.2.1); encodes where the message came from and how urgent it is. |
| RFC 5424 | "Modern syslog" | The 2009 structured format: `<PRI>1 TS HOST APP PROCID MSGID SD MSG`, replaces the legacy RFC 3164 BSD format. |
| RELP | "Reliable syslog" | Reliable Event Logging Protocol (RFC 3195) — TCP-based, replay-on-restart, used in `rsyslog`'s `omrelp`. |
| TLS syslog | "Encrypted syslog" | RFC 5425 — TLS-wrapped TCP syslog, mandatory when syslog leaves the trusted network. |
| NTP / chrony | "Time sync" | Network Time Protocol (RFC 5905); chrony is the modern Linux implementation, with `chronyd` (daemon) and `chronyc` (CLI). |
| Stratum | "How many hops from GPS" | NTP layer number — stratum 1 = directly connected to GPS/atomic clock; each sync adds one. |
| SD-ELEMENT | "Structured fields" | RFC 5424 typed parameters like `[origin@32473 software="rsyslogd" version="8.2402.0"]` — the SIEM correlation key. |

## Further Reading

- [RFC 5424](https://www.rfc-editor.org/rfc/rfc5424) — The Syslog Protocol (the 2009 structured format)
- [RFC 3164](https://www.rfc-editor.org/rfc/rfc3164) — The BSD Syslog Protocol (legacy, single-line)
- [RFC 3195](https://www.rfc-editor.org/rfc/rfc3195) — Reliable Delivery for Syslog (RELP)
- [RFC 5425](https://www.rfc-editor.org/rfc/rfc5425) — TLS Transport Mapping for Syslog
- [RFC 5905](https://www.rfc-editor.org/rfc/rfc5905) — Network Time Protocol Version 4
- [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339) — Date and Time on the Internet (the timestamp format syslog uses)
- [`rsyslog` documentation](https://www.rsyslog.com/doc/) — the de facto Linux syslog, supports RFC 5424 + TLS + RELP
- [`chrony` documentation](https://chrony.tuxfamily.org/documentation.html) — the modern NTP implementation
- [`ntpsec` documentation](https://docs.ntpsec.org/latest/) — a hardened NTP reference implementation