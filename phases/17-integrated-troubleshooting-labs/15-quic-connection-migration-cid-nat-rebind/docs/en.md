# QUIC Connection Migration and CID under NAT Rebinding

> A user on a mobile client opens a QUIC connection to a media server at `198.51.100.10:443`, the client is on Wi-Fi (`192.168.1.42:54000`), the connection works for two minutes, and then the user walks out of range. The phone silently roams to LTE (`10.43.7.91:52411`), the NAT on the home router rebinds, the four-tuple `(local_ip, local_port, remote_ip, remote_port)` that the server's conntrack table had pinned vanishes, and an HTTP/3 stream in flight stalls. TCP would have died. The connection survives because QUIC identifiers sessions by **Connection ID** (RFC 9000 §17.2, variable length up to 20 bytes), not by the 4-tuple — but only if the server's `NEW_CONNECTION_ID` frames keep the new path validated, the client's `PATH_CHALLENGE`/`PATH_RESPONSE` exchange completes within the `max_path_challenge_frames` ceiling, and the migration is not a deliberate change of the *server's* address. This lab reproduces the failure when the server's `active_connection_id_limit` was set to 2, the peer retired CIDs too eagerly, and the migrated path never received a `PATH_RESPONSE` — so the new path was treated as unvalidated and the stream silently drained to `0` for 30 seconds before the connection died with `CONNECTION_CLOSE(0x0c, "Path validation failed")`. The fix is to bump `active_connection_id_limit` to 8, keep spare unused CIDs available, and instrument the qlog to see the path validation state machine.

**Type:** Lab
**Languages:** Python, shell, quiche, qlog
**Prerequisites:** Phase 10 UDP and the QUIC header layout, Phase 11 congestion control, RFC 9000 §9 (connection migration)
**Time:** ~110 minutes

## Learning Objectives

- Diagnose a QUIC connection that survives a Wi-Fi-to-LTE roam but then stalls and closes: read qlog, find the `PATH_CHALLENGE` and the missing `PATH_RESPONSE`, and explain the path validation state machine (RFC 9000 §8.2).
- Distinguish connection migration from NAT rebinding: explain why the four-tuple change is not visible to the application, and why the Connection ID is the binding identifier that survives a NAT rebind.
- Compute the spare-CID budget: `active_connection_id_limit` (transported in the TLS `transport_parameters` extension) minus the number of peer-issued CIDs the server has retired, and explain why `0` spare CIDs blocks migration.
- Read a QUIC long-header / short-header packet and identify the DCID/SCID, the spin bit, and the `0x1d` packet type for Initial, `0x06` for 0-RTT, `0x02` for Handshake, `0x43` for 1-RTT.
- Use `quiche` or `aioquic` to construct a reproducible failure: a client that switches source IP mid-connection, a server with a too-low `active_connection_id_limit`, and a `qlog` trace that shows the stall.
- Build a Python simulator that walks the QUIC path validation state machine (`PATH_CHALLENGE` → `PATH_RESPONSE` → `PATH_VALIDATED`) and prints the verdict that matches the production qlog.

## The Problem

The on-call ticket reads: "User on Android reports that the live audio stream cuts out about 30 seconds after they leave home. Reconnecting fixes it. We see `CONNECTION_CLOSE(TransportError(0x0c, "Path validation failed"))` in the client logs and a flood of `SCID` updates on the wire." The application team owns the streaming client; the platform team owns the QUIC server stack. Each thinks the other is at fault.

The mobile client uses a `quiche`-based SDK. It opens a connection on Wi-Fi, gets a 12-byte Connection ID, sends a few hundred media packets, then the user walks out of range. The phone tears down the Wi-Fi link, brings up LTE, and the SDK tries to keep the QUIC session alive. The server sees a 1-RTT packet from a brand-new four-tuple, looks at the DCID, finds the connection, and starts a path validation: it sends a `PATH_CHALLENGE` with an 8-byte random token to the new client address. If the client answers with a `PATH_RESPONSE` carrying the same token within the validation timeout, the path is marked `Validated` and traffic continues. If the response never arrives, the server treats the path as unvalidated and, after `path_validation_timeout` (default 3 × PTO), closes the connection.

The qlog in the ticket shows: `PATH_CHALLENGE` issued by the server at `t=+128.411`, no matching `PATH_RESPONSE` within `path_validation_timeout`, then `CONNECTION_CLOSE(0x0c, "path validation failed")` at `t=+132.290`. The reason the response never arrived is more interesting than a network drop: the server issued exactly two CIDs (`active_connection_id_limit=2`), the client used one for the active path, retired the other after the Wi-Fi interface went down, and the NAT rebind reset the server's view of the client's port. The server's path validation packet was sent to the right IP but the *old* port (because the server's `peer_address` was cached from a `NEW_CONNECTION_ID` that was not yet confirmed on the new path), and the client's NAT-rebind broke the return route. Once the spare-CID pool is empty, no new CID can be issued, and migration collapses.

The diagnostic discipline is to read three pieces of evidence together: the qlog's `transport:path_validation` event, the count of `NEW_CONNECTION_ID` frames received and `RETIRE_CONNECTION_ID` frames sent, and the server's `transport_parameters.active_connection_id_limit`. The fix is not on the network — it is in the server's `transport_parameters`.

## The Concept

### The four-tuple is not the identity

TCP and TLS-over-TCP bind a session to the 4-tuple `(local_ip, local_port, remote_ip, remote_port)`. A NAT rebind that changes any one of those four values terminates the session, no matter how healthy the application is. QUIC's design choice (RFC 9000 §1) is to make the **Connection ID** the session identifier. A QUIC endpoint MAY use any 4-tuple to send a packet, and the peer identifies the connection purely by the DCID. This is what makes "connection migration" (RFC 9000 §9) possible.

The trade-off is that the receiving endpoint must keep a map from CID to internal state, and the DCID field must be long enough that collision risk is negligible. RFC 9000 §17.2 sets the CID at up to 20 bytes, and §18.2 requires the server to set `active_connection_id_limit` to a value (typically 4 or 8) so the client always has spares.

### The path validation state machine

A peer that wants to use a new local address must prove it can both receive and send on the new path. The protocol is a challenge-response (RFC 9000 §8.2):

```
PathStatus:   Unknown  -->  Validating  -->  Validated
                              |
                              v
                           Failed (after path_validation_timeout)
```

- The validating endpoint sends a `PATH_CHALLENGE` frame containing an 8-byte unpredictable token on the new path.
- The peer echoes the same token in a `PATH_RESPONSE` frame on the *same* path.
- Receipt of a matching `PATH_RESPONSE` transitions the path to `Validated`; the endpoint may now use it for general traffic.
- If no `PATH_RESPONSE` arrives within the validation timeout, the path transitions to `Failed` and the connection is closed with `CONNECTION_CLOSE(0x0c, "path validation failed")` (transport error code 0x0c is `PATH_RESPONSE_ERROR` in RFC 9000 §22.14).

`PATH_CHALLENGE` and `PATH_RESPONSE` are both 9-byte frames: 1-byte type (`0x1a` challenge, `0x1b` response) plus 8 bytes of token. They can be coalesced in 1-RTT packets alongside data frames, so the cost of validation is small — but only if the server actually emits them.

### Why the four-tuple change is "invisible" to the application

When the server receives a 1-RTT packet on the new four-tuple, it does not hand the four-tuple to the application. It looks up the connection by DCID, finds the application stream IDs, and continues sending data on any local address the kernel has open. The application sees no event at all — the migration is a transport-layer event. This is why the user-perceived bug is "audio cuts out 30 seconds later" rather than "connection reset."

### The spare-CID budget

`active_connection_id_limit` is negotiated in the TLS `transport_parameters` extension (RFC 9001 §5.1). It is the maximum number of CIDs the peer may issue. If the server sets it to 2, the client may receive at most 2 CIDs. If the client uses both, retires one, and the server tries to issue a third because the path validation has reset, the server cannot — the limit is a hard cap. The migration then hangs waiting for a `PATH_RESPONSE` that the server will not send because it has no spare CID to put the response on.

| Quantity | Where it lives | Why it matters |
|---|---|---|
| `active_connection_id_limit` | Server's `transport_parameters` | Hard cap on CID issuance; too low = migration breaks |
| `NEW_CONNECTION_ID` frame | Server → client, 1+RTT | Issues a new CID, with `retire_prior_to` |
| `RETIRE_CONNECTION_ID` frame | Client → server, 1-RTT | Tells the server which CID is no longer in use |
| Spare CIDs | Server-side state | `(active_connection_id_limit − # CIDs issued) + # CIDs retired` |
| Spare CIDs == 0 | — | Server cannot issue a new CID on a new path; migration will fail |

The correct operational setting for a mobile-facing service is 8 (the QUIC default in many stacks; `aioquic` defaults to 8 as well). Setting it to 2 is a common "it works in the lab because the client never moves" misconfiguration.

### What a real qlog of the failure looks like

A `qlog` file is JSON-lines with one event per line. The relevant events for a migration failure look like:

```json
{"time": 128.411, "name": "transport:path_challenge_sent", "data": {"path_id": 1, "token": "a3:1b:..."}}
{"time": 128.413, "name": "transport:packet_sent", "data": {"header": {"packet_type": "1RTT", "dcid": "..."}}}
{"time": 132.290, "name": "transport:connection_close", "data": {"error_code": 12, "reason": "path validation failed"}}
```

A `PATH_RESPONSE` event from the client at, say, `t=128.601` would have moved the path to `Validated` and prevented the close. The diagnostic question is: *why didn't the client answer?* — and the answer is almost always one of three things: (a) the server's `PATH_CHALLENGE` reached an outdated client port because of a stateful NAT, (b) the client hit a packet filter on the LTE path that dropped UDP/443, or (c) the server never sent the challenge because it ran out of spare CIDs.

### How the simulator models this

`code/main.py` does not sniff a live qlog. It runs a deterministic state machine that mirrors the relevant QUIC behaviors: the server's CID pool, the path validation timer, and the client's CID-retirement policy. The user picks a scenario (`--scenario spare_cid_exhausted` is the one in the ticket), and the simulator emits a verdict matching the production qlog. The simulator is a **reference oracle**, not a sniffer — it lets you rehearse the diagnosis in seconds.

## Build It

1. **Capture a real qlog.** Run a `quiche`-based server with `active_connection_id_limit=2`, connect an `aioquic` client over a network namespace, then migrate the client's source IP. Save the qlog to `/tmp/migration.qlog`.
2. **Parse the qlog.** Filter on `transport:path_challenge_sent`, `transport:path_response_received`, `transport:connection_close`. Confirm the timeline matches the ticket.
3. **Run the reference oracle.** `python3 code/main.py --scenario spare_cid_exhausted --limit 2` should produce the same verdict: "Path validation failed; no spare CID available."
4. **Re-run with the fix.** Restart the server with `active_connection_id_limit=8` and re-capture. The simulator's `Validated` transition should match the production trace.
5. **Ship the runbook.** A two-page runbook that lists, in order, the three evidence sources to read on a migration-stall ticket.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm spare-CID exhaustion | Server `transport_parameters.active_connection_id_limit` | Value ≥ 4 for mobile-facing services; ≥ 8 for the conservative default |
| Confirm challenge was sent | qlog `transport:path_challenge_sent` | One event per new path; token present |
| Confirm response was received | qlog `transport:path_response_received` | Same token echoed; path transitions to `Validated` |
| Confirm close cause | qlog `transport:connection_close` | `error_code` 0x0c = `PATH_RESPONSE_ERROR` |
| Verify the fix | Re-capture after bumping the limit | `path_validated` events for both old and new paths |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page **QUIC migration triage runbook** that maps each qlog signal to the responsible layer (server, client, network).
- A diff of the server's `transport_parameters` before/after the fix, with the rationale for the chosen limit.

Start from `outputs/prompt-quic-connection-migration-cid-nat-rebind.md` and paste in the actual qlog lines from your capture.

## Exercises

1. The server sets `active_connection_id_limit=1`. The client issues zero `RETIRE_CONNECTION_ID` frames. Will migration succeed? Why or why not?
2. A `PATH_CHALLENGE` is sent at `t=128.411`. The `PATH_RESPONSE` arrives at `t=128.601`. The `path_validation_timeout` is `3 × PTO = 1.5s`. Did the path validate? Compute the validation budget consumed.
3. The server emits a `NEW_CONNECTION_ID` with `sequence_number=5` and `retire_prior_to=3`. What does the client infer about CIDs 3 and 4? What is the resulting spare-CID count if the limit was 8?
4. A mobile carrier CGN drops UDP/443 to its own LTE customers. The qlog shows a `PATH_CHALLENGE` from the server but no `PATH_RESPONSE` from the client. Is this a server bug, a client bug, or a network bug? Justify with the `error_code` field.
5. Compute the spare-CID budget after the following sequence: limit=4, server issues CIDs 0, 1, 2, 3; client retires 0 and 1; server then issues 4, 5; client retires 2. How many spares remain?
6. A `quiche` client has its `disable_active_migration=true` setting. The user roams from Wi-Fi to LTE. Predict the qlog events in order, and explain why the migration is *not* attempted.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Connection ID | "QUIC's connection identifier" | The per-session opaque token in the QUIC header that binds packets to a connection, independent of 4-tuple (RFC 9000 §17.2) |
| Connection migration | "QUIC roaming" | The ability to change the local 4-tuple without dropping the connection (RFC 9000 §9) |
| Path validation | "QUIC's NAT check" | `PATH_CHALLENGE`/`PATH_RESPONSE` round-trip that proves reachability on a new local address (RFC 9000 §8.2) |
| `active_connection_id_limit` | "CID cap" | Transport parameter that caps how many `NEW_CONNECTION_ID` frames the peer may issue (RFC 9001 §5.1) |
| `transport_parameters` | "QUIC's TLS options" | TLS extension that carries QUIC's configuration: CID limit, initial max data, ack delay, etc. (RFC 9001) |
| 0x0c / `PATH_RESPONSE_ERROR` | "Path validation error" | Transport error code returned in `CONNECTION_CLOSE` when path validation fails (RFC 9000 §22.14) |
| `NEW_CONNECTION_ID` frame | "New CID" | Frame type 0x18 that issues a spare CID; carries a sequence number and `retire_prior_to` (RFC 9000 §19.15) |
| `RETIRE_CONNECTION_ID` frame | "Drop CID" | Frame type 0x19 that tells the peer the CID is no longer in use (RFC 9000 §19.16) |

## Further Reading

- RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport (CID layout, frames, path validation, connection migration, error codes)
- RFC 9001 — Using TLS to Secure QUIC (transport_parameters extension definition)
- RFC 9221 — Bootstrapping WebSockets with HTTP/3 (background on HTTP/3 framing over QUIC)
- `quiche` source — `quiche-proto` path validation state machine (`PathState` enum: `Unknown`, `Validating`, `Validated`, `Failed`)
- `qlog` schema — `transport:path_*` events and the `transport:connection_close` event with `error_code` semantics
- Iyengar & Thomson, "QUIC: A UDP-Based Multiplexed and Secure Transport" (Internet-Draft history, design rationale)
