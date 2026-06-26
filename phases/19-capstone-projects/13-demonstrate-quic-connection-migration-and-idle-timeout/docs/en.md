# Demonstrate QUIC Connection Migration and Idle Timeout

> Simulate QUIC's connection-level identity via Connection IDs, demonstrate seamless migration when the client's IP changes, and model the idle timeout that tears down inactive connections.

**Type:** Capstone
**Languages:** Python, Wireshark, openssl
**Prerequisites:** Phase 11 TCP/UDP lessons; understanding of UDP, TLS 1.3 handshake, and connection state
**Time:** ~140 minutes

## Learning Objectives

- Model QUIC connection establishment: Initial packets, handshake, and Connection ID negotiation
- Demonstrate connection migration: when the client's IP/port changes, the connection survives because QUIC identifies connections by Connection ID, not 4-tuple
- Simulate path validation: the server probes the new path before migrating traffic
- Model idle timeout: connections that are inactive beyond the negotiated timeout are silently closed
- Compare QUIC connection migration to TCP, which breaks when the 4-tuple changes
- Implement loss recovery across path migration: packets in flight on the old path are retransmitted on the new path

## The Problem

TCP identifies a connection by its 4-tuple (source IP, source port, destination IP, destination port). When a mobile device switches from Wi-Fi to cellular, the source IP changes, the 4-tuple breaks, and the TCP connection dies. The application must reconnect, losing in-flight data and adding latency.

QUIC solves this with Connection IDs (CIDs). A QUIC connection is identified by a CID, not by the 4-tuple. When the client migrates to a new network (new IP, new port), it continues sending packets with the same CID. The server recognizes the connection, validates the new path, and continues sending data on the new path. No reconnection, no data loss, no user-visible disruption.

Additionally, QUIC has a built-in idle timeout. If no packets are exchanged for a negotiated duration (default 30 seconds), the connection is silently closed without any explicit teardown. This is cleaner than TCP's TIME-WAIT and avoids zombie connections.

This capstone asks you to simulate QUIC connection establishment, demonstrate connection migration across a network change, model path validation and loss recovery, and implement idle timeout. You must compare this to TCP behavior where the same network change kills the connection.

## The Approach

The simulation follows six stages, each building on the previous. Work through them in order — each stage produces output that feeds into the next.

**Stage 1: QUIC Handshake Simulation**

Model the three-phase QUIC handshake: the client sends an Initial packet carrying a randomly chosen source Connection ID (8 bytes, e.g., `0xDEADBEEF01234567`) along with the TLS ClientHello; the server responds with its own Initial and Handshake packets, issuing four NEW_CONNECTION_ID frames so the client has a pool of CIDs to use during migration; the exchange completes with 1-RTT packets confirming the Handshake and establishing the connection state keyed by CID on both sides. After this stage you should have a `QUICConnection` object holding the negotiated CID pool, the current path, and separate packet number counters for the Initial, Handshake, and 1-RTT packet number spaces.

**Stage 2: Normal Data Transfer**

Send 10 stream data packets on the established path `192.168.1.5:54321 → 10.0.0.1:443` using Destination Connection ID `0xDEADBEEF01234567` and incrementing 1-RTT packet numbers starting at 0. Each packet carries a STREAM frame with a stream ID, offset, and payload; the receiver sends ACK frames that reference the received packet numbers. Log every packet number, its CID, the source/destination 4-tuple, and the ACK round-trip time so you can compare pre-migration and post-migration latency in Stage 5.

**Stage 3: Network Change**

Simulate a Wi-Fi to cellular handoff: the client's address abruptly changes from `192.168.1.5:54321` to `10.0.0.50:61234` while the server address remains `10.0.0.1:443`. The client does not tear down anything — it simply sends the next 1-RTT packet with the same Destination CID but from the new source 4-tuple. The server receives a packet from an unknown source address carrying a known CID; this is the migration trigger. At the moment of migration, exactly 4 packets are in flight on the old path (packet numbers 6, 7, 8, 9 sent but not yet ACKed), which sets up the loss recovery scenario in Stage 5.

**Stage 4: Path Validation**

Upon detecting the new source address, the server must validate the new path before migrating traffic to it. The server generates a cryptographically random 8-byte challenge token and sends a PATH_CHALLENGE frame to `10.0.0.50:61234`; the client echoes the exact token back in a PATH_RESPONSE frame on the same path. The server verifies the token matches, marks the new path as validated, and promotes it to the primary path — all subsequent data frames go to `10.0.0.50:61234`. Log the round-trip time of the PATH_CHALLENGE/PATH_RESPONSE exchange; this is the migration overhead cost that you will compare to TCP reconnection cost in Stage 5.

**Stage 5: Loss Recovery Across Migration**

The 4 packets that were in flight on the old path (packet numbers 6–9) will never be ACKed because the old path is gone. After the migration completes, the QUIC loss detection timer fires and declares those packets lost. Retransmit their STREAM frame payloads in new packets (new packet numbers) on the new path `10.0.0.50:61234 → 10.0.0.1:443`. Measure two latency figures: the QUIC overhead (PATH_CHALLENGE RTT + retransmission RTT) and the equivalent TCP overhead (TCP SYN/SYN-ACK/ACK reconnect + TLS handshake). The QUIC overhead should be roughly one RTT; the TCP overhead should be three to five RTTs depending on TLS session resumption.

**Stage 6: Idle Timeout**

After all data has been transferred, simulate 31 seconds of inactivity with no PING keepalive frames sent by either side. At the 30-second mark the idle timeout expires; both sides independently discard their connection state and consider the connection closed. There is no FIN, no RST, no CONNECTION_CLOSE frame — the connection simply ceases to exist. Log the idle duration, the timeout threshold, and the final connection state on both sides. Then simulate the same scenario with TCP: after 31 seconds of inactivity the TCP connection is still open (it has no idle timeout unless SO_KEEPALIVE is set), and a load balancer must send a FIN to reclaim the slot — contrast this with QUIC's automatic silent close.

## Build It

1. Define the core dataclasses. `QUICConnection` holds `cid: bytes` (8 bytes), `path: tuple[str, int, str, int]` (src_ip, src_port, dst_ip, dst_port), `packet_number: dict[str, int]` keyed by packet number space (`"initial"`, `"handshake"`, `"one_rtt"`), `cid_pool: list[bytes]`, and `last_activity: float`. `QUICPacket` holds `pn_space: str`, `packet_number: int`, `dcid: bytes`, `frames: list`. `PathState` holds `address: tuple`, `validated: bool`, `challenge: bytes | None`.

2. Implement the handshake. Client calls `send_initial(src_cid=bytes.fromhex("DEADBEEF01234567"))`. Server responds with Initial + Handshake packets and calls `issue_cids(count=4)` to populate the client's `cid_pool` via NEW_CONNECTION_ID frames. Both sides advance through `"initial"` → `"handshake"` → `"one_rtt"` packet number spaces, resetting the counter to 0 at each transition.

3. Implement data transfer on `192.168.1.5:54321 → 10.0.0.1:443`. Send 10 STREAM frames with stream ID 0, offsets 0 through 9, each carrying an 80-byte payload. Use `one_rtt` packet numbers 0–9. Receiver ACKs each packet; log each ACK with the measured RTT in milliseconds.

4. Implement migration detection. When the server receives a packet from a new 4-tuple but a known `dcid`, it sets `conn.path = new_path` and calls `start_path_validation(new_path)`. The old path enters a draining state — no new data is sent to it, but existing ACKs from it are still accepted for a 3× PTO window.

5. Implement path validation. `start_path_validation` generates `challenge = secrets.token_bytes(8)`, creates a `PathState(address=new_path, validated=False, challenge=challenge)`, and sends `PATH_CHALLENGE(challenge)` to the new address. When `PATH_RESPONSE(token)` arrives and `token == challenge`, set `PathState.validated = True` and promote the new path to primary.

6. Implement loss recovery. After migration, set a loss detection timer for the 4 in-flight packets (packet numbers 6–9). When the timer fires, call `declare_lost([6,7,8,9])` which retransmits each packet's STREAM frame payload in new 1-RTT packets (numbers 10–13) on the new path. Log old packet number, new packet number, and retransmission RTT.

7. Implement idle timeout. Store `conn.last_activity = time.monotonic()` on every sent or received packet. A background check every second computes `idle = time.monotonic() - conn.last_activity`. When `idle > conn.idle_timeout` (default 30 s), call `conn.close(reason="idle_timeout")` which discards state silently. For the TCP comparison, model a `TCPConnection` with no idle timeout: after 31 s it is still open and a load balancer sends `FIN` to reclaim it.

8. Run `code/main.py` and verify the output files. The migration timeline should show Stage 1 through Stage 6 with timestamps. The loss recovery log should show exactly 4 retransmissions. The idle timeout log should show closure at the 30-second mark. The TCP comparison should show three to five RTTs of reconnection overhead versus one RTT for QUIC path validation.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| QUIC handshake completes | `outputs/quic-connection-log.txt` shows Initial → Handshake → 1-RTT sequence with four CIDs issued | Three packet number spaces printed; `cid_pool` length = 4 after handshake |
| Migration trigger detected | Log line `[MIGRATION] new path 10.0.0.50:61234 detected, old path 192.168.1.5:54321` | Appears exactly once, at the moment packet number 10 arrives from new address |
| Path validation succeeds | `outputs/migration-timeline.txt` shows `PATH_CHALLENGE sent → PATH_RESPONSE received → path promoted` | Challenge token echoed correctly; `PathState.validated = True` within one RTT |
| Packet delivery continuity | Stream data resumes on new path with no gap in application payload offsets | Offsets 0–9 delivered on old path, offsets re-sent on new path without duplication or gap |
| Loss recovery fires | `outputs/loss-recovery.txt` lists packets 6–9 declared lost and retransmitted as 10–13 | Exactly 4 retransmissions; all retransmissions use new path 4-tuple |
| Idle timeout closes connection | `outputs/idle-timeout.txt` shows connection closed after 30 s with no FIN or RST | Final state `CLOSED`; no CONNECTION_CLOSE frame emitted; TCP comparison shows FIN required |
| TCP comparison quantified | `outputs/quic-vs-tcp-comparison.txt` shows RTT counts side by side | QUIC overhead = 1 RTT (path validation); TCP overhead = 3–5 RTTs (reconnect + TLS) |

## Ship It

**QUIC state diagram** — Draw the connection state machine covering all six stages: `IDLE → HANDSHAKE → CONNECTED → MIGRATING → VALIDATED → DRAINING → CLOSED`. Label each transition with the frame or event that triggers it (Initial packet, Handshake complete, migration detected, PATH_CHALLENGE sent, PATH_RESPONSE received, idle timeout, loss recovery complete). Include the TCP state machine on the same diagram for comparison; annotate the state that TCP cannot reach (migration without reconnect).

**Migration timeline** — Produce a chronological timeline in `outputs/migration-timeline.txt` that lists every event with a simulated timestamp in milliseconds: handshake start, each packet sent and ACKed, migration trigger, PATH_CHALLENGE, PATH_RESPONSE, path promotion, loss declarations, retransmissions, and idle timeout. This timeline is the primary artifact for explaining QUIC migration to someone who has not seen it before.

**TCP vs QUIC comparison chart** — Create `outputs/quic-vs-tcp-comparison.txt` with a table covering: connection identity mechanism, behavior on IP change, reconnection required, in-flight data fate, path validation mechanism, idle timeout behavior, and latency overhead on migration. Fill in both columns for every row. The chart should be self-contained — a reader should understand the tradeoff without reading any other file.

**Idle timeout runbook for load balancers** — Write `outputs/quic-migration-runbook.md` with operational guidance for load balancers that proxy QUIC. Cover: why CID-based routing is required (IP-based routing breaks on migration), how to configure the idle timeout to match the QUIC transport parameter, how to detect a migrated connection at the load balancer, and how to update the routing table when a CID moves to a new client address. Include a section on what happens when the idle timeout on the load balancer is shorter than the one negotiated by the endpoints.

## Exercises

1. **Simultaneous migration on both sides** — Model a scenario where both the client and server change addresses at the same time (e.g., both are on mobile networks). Which side initiates path validation? How does QUIC prevent a deadlock where each side waits for the other to validate? What does RFC 9000 say about simultaneous migration?

2. **Multiple CIDs in active use** — Issue eight CIDs instead of four. Send packets concurrently using different CIDs on different paths (simulating a multipath scenario). Track which CID is associated with which path. What happens when the server retires a CID that the client is still using? Implement the `RETIRE_CONNECTION_ID` frame and test graceful retirement.

3. **NAT rebinding (server-side perspective)** — Simulate NAT rebinding: the client's IP stays the same but the NAT box assigns a new source port (e.g., 54321 → 54399) without the client's knowledge. From the server's perspective this looks identical to client migration. How should the server distinguish NAT rebinding from intentional migration? What anti-amplification measures apply before path validation completes?

4. **Connection ID rotation for privacy** — Implement mid-connection CID rotation. After every 5 packets, the client asks the server to issue a new CID and retires the old one. This prevents passive observers from correlating packets across a long session. Verify that the connection survives multiple rotations without interruption. Measure the overhead of rotation (extra NEW_CONNECTION_ID and RETIRE_CONNECTION_ID frames) in bytes per rotation cycle.

5. **0-RTT resumption after migration** — After an idle timeout closes the connection, model the client reconnecting with a cached session ticket using 0-RTT. The client sends application data in the very first packet before the handshake completes. How does this interact with connection migration — can the client send 0-RTT data on the new path immediately, or must it wait for the handshake to complete on the new path first? What replay attack risk does 0-RTT introduce?

6. **Comparing QUIC migration with MPTCP** — Research MPTCP (RFC 8684) and implement a simplified model of its subflow-addition mechanism. Compare it to QUIC migration: MPTCP adds new subflows alongside existing ones while QUIC migrates the entire connection to a new path. Which performs better for a sudden address change with 4 packets in flight? Which is easier to deploy through NAT? Produce a side-by-side latency table.

7. **Load balancer implications of CID-based routing** — Extend the simulation to include a layer-4 load balancer that routes QUIC packets to one of three backend servers based on the Destination CID. When the client migrates to a new IP, the load balancer must update its routing table to send all packets with that CID to the same backend. Implement the routing table update and measure the window during migration where packets could be misrouted. How does QUIC's server-chosen CID (encoded with the server ID per draft-ietf-quic-load-balancers) solve this?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Connection ID (CID) | A QUIC identifier | An opaque byte string (typically 8 bytes) chosen by each endpoint to name one side of a connection; the server's Destination CID is what load balancers and the network see |
| Path validation | Checking the new path | A challenge-response exchange (PATH_CHALLENGE / PATH_RESPONSE) that proves the new address is reachable and not spoofed before traffic is migrated to it |
| PATH_CHALLENGE | The probe frame | A QUIC frame containing a random 8-byte token sent to a new path to verify reachability; the recipient must echo the token back in a PATH_RESPONSE |
| PATH_RESPONSE | The echo frame | A QUIC frame that echoes the PATH_CHALLENGE token verbatim; its arrival on the new path proves the path is bidirectionally reachable |
| 4-tuple | The network identifier | (src_ip, src_port, dst_ip, dst_port); the complete network-layer identity of a flow; TCP uses this as the connection key, QUIC uses CID instead |
| Connection migration | Surviving an address change | The QUIC mechanism by which a connection continues after the client's 4-tuple changes; enabled by CID-based identity and path validation |
| Idle timeout | The silent close timer | A transport parameter negotiated during the handshake; if no packet is received for this duration, both sides independently close the connection without sending any frame |
| PING frame | The keepalive frame | A zero-length QUIC frame sent to elicit an ACK and reset the idle timer; used when application data is not flowing but the connection must be kept alive |
| 0-RTT | Zero round-trip resumption | A TLS 1.3 feature that allows a client to send encrypted application data in the first flight of packets using a session ticket from a previous connection, reducing reconnection latency to zero additional round trips |
| 1-RTT | Established encryption | The packet number space used for application data after the TLS handshake completes; uses the application traffic keys derived from the handshake |
| Initial packet | The first QUIC packet | A QUIC packet type used for the first flight of the handshake; carries the TLS ClientHello or ServerHello and is encrypted with keys derived from the Destination CID |
| Packet number space | The ACK namespace | QUIC maintains three independent packet number sequences — Initial, Handshake, and 1-RTT — so that ACKs in one space cannot be confused with ACKs in another; each space starts at 0 |

## Further Reading

- RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport. Sections 8 (address validation), 9 (connection migration), and 10.1 (idle timeout) are the primary references for this capstone. https://www.rfc-editor.org/rfc/rfc9000
- RFC 9001 — Using TLS to Secure QUIC. Covers the packet number spaces, key derivation from the Destination CID for Initial packets, and the handshake keys used in Stages 1 and 2 of this capstone. https://www.rfc-editor.org/rfc/rfc9001
- RFC 9002 — QUIC Loss Detection and Congestion Control. Defines the loss detection timer and the rules for declaring packets lost — the mechanism behind Stage 5 (loss recovery across migration). https://www.rfc-editor.org/rfc/rfc9002
- draft-ietf-quic-load-balancers — QUIC-LB: Generating Routable QUIC Connection IDs. Explains how servers encode a backend server token into the Connection ID so that load balancers can route packets by CID without reading the encrypted payload — directly relevant to Exercise 7. https://datatracker.ietf.org/doc/draft-ietf-quic-load-balancers/
- Iyengar, J. and M. Thomson — "QUIC: A UDP-Based Multiplexed and Secure Transport" (ACM SIGCOMM 2015 workshop paper). Provides the original design rationale for CID-based connection identity and migration, with latency measurements comparing QUIC migration overhead to TCP reconnection. Available via ACM Digital Library.
