# Kerberos: tickets, KDC, and TGS handshake

> Kerberos V5 (RFC 4120) splits the trusted third party of Needham-Schroeder into two servers — an Authentication Server (AS) that verifies a user's password at login and a Ticket-Granting Server (TGS) that mints per-service tickets on demand — and adds synchronized clocks so tickets can carry an expiry time instead of a round-trip nonce challenge. The flow: Alice types her password into a workstation; the workstation sends `A, TGS` in plaintext to the AS; the AS returns `K_A(TGS, K_S,tgs, t_exp)` plus a TGT `K_TGS(A, K_S,tgs, t_exp)`. Alice decrypts with `K_A` (derived from her password via PBKDF2 / string-to-key), extracts `K_S,tgs`, and uses it to ask the TGS for a service ticket for Bob: `K_S,tgs(B, t_req, TGT)`. The TGS replies `K_S,tgs(B, K_AB, t_exp), K_B(A, K_AB, t_exp)`. Alice forwards the service ticket to Bob, who decrypts it under his long-term key `K_B` and recovers `K_AB`. Every step binds a timestamp `t` so a replayed ticket from an hour ago is rejected, replacing the nonce round-trips of Needham-Schroeder with a single signed lifetime. This lesson implements the full six-message Kerberos V5 exchange (RFC 4120 §3.1 / §3.2 / §3.3) in pure Python, with cross-realm TGS referrals and clock-skew handling.

**Type:** Lab
**Languages:** Python
**Prerequisites:** Phase 19 (Needham-Schroeder), Phase 14 (HMAC, AES-style symmetric crypto), Phase 18 (certificates for cross-realm PKINIT)
**Time:** ~90 minutes

## Learning Objectives

- Draw the six-message Kerberos V5 handshake (AS-REQ/AS-REP, TGS-REQ/TGS-REP, AP-REQ/AP-REP) with the exact key names from RFC 4120 §3.
- Derive Alice's long-term key `K_A` from her password using a string-to-key function (PBKDF2-HMAC-SHA256, 4096 iterations, 16-byte salt) and explain why the password never crosses the wire.
- Walk a service-ticket request through the TGS, identifying the TGT envelope `K_TGS(...)` and the service ticket envelope `K_B(...)` and what each proves.
- Configure `clockskew` (default 5 minutes per RFC 4120 §3.1.3) and reproduce the "KRB_AP_ERR_SKEW" failure that operators see when NTP drifts.
- Add a cross-realm TGT: Alice's realm issues a referral ticket for a foreign TGS, allowing her to obtain service tickets in another administrative domain.
- Compare Kerberos to NTLM, SAML, and OIDC: when is a ticket-granting architecture the right tool, and when is a token-based one?

## The Problem

You have ten thousand employees and two thousand services. Each employee should be able to log into any workstation, then access only the services their role grants them. You cannot give every workstation a copy of every service's password. You cannot require every service to know every user's password. You cannot trust the network — any of those workstations sits on a conference-room table where anyone can plug in a USB stick and walk away.

The 1988 answer (MIT Project Athena, Steve Miller + Cliff Neuman) was Kerberos: split the trusted third party in two, use tickets that expire, and avoid sending the user's password anywhere. By 2005 the protocol was at V5, the IETF standardized it as RFC 4120, and Microsoft adopted it as the default authentication for Active Directory. Today it is the authentication backbone of roughly 80% of enterprise Windows networks and most large Hadoop deployments.

The reason it is interesting to study in 2026 is that the same architecture — AS + TGS + tickets + synchronized clocks — shows up in every modern federated identity system, just rebranded: OIDC's `id_token` is a ticket, an OAuth2 authorization server is a TGS, and SAML assertions carry the same `NotOnOrAfter` constraint that Kerberos tickets have. Once you understand Kerberos, every other enterprise auth system reads as a variation.

## The Concept

### The six messages

```
Client                          AS                          TGS                         Server
   |--- 1. AS-REQ (A, TGS, t_req) ---->|                      |                            |
   |                                    |  verify A's request  |                            |
   |<-- 2. AS-REP (K_A(...), TGT) -----|                      |                            |
   |                                                                       |
   |--- 3. TGS-REQ (B, t_req, Auth=K_S,tgs(t_req), TGT) -->|              |
   |                                    |                    |  check TGT, t_req      |
   |                                    |                    |  check timestamp        |
   |<-- 4. TGS-REP (K_S,tgs(...), ticket_B) -----------------|              |
   |                                                                       |
   |--- 5. AP-REQ (ticket_B, K_AB(t_req)) ------------------------------->|
   |                                                                       |  open ticket_B
   |                                                                       |  verify t_req
   |<-- 6. AP-REP (K_AB(t_req-1)) [optional mutual auth] ----------------|
```

The two-phase indirection (AS gives you a TGT, TGT is used to fetch service tickets) is the key efficiency: Alice enters her password once at login. The AS verifies her and returns a TGT valid for ~10 hours. Every subsequent service request reuses that TGT — no more password touches, no more AS involvement.

### Key names from RFC 4120

| Symbol | Meaning | Lifetime |
|---|---|---|
| `K_A` | Alice's long-term key derived from her password | Until she changes her password |
| `K_TGS` | The TGS's long-term key | Rotated per realm policy |
| `K_B` | Bob the server's long-term key | Rotated per service |
| `K_S,tgs` | Session key between Alice and the TGS | ~minutes to hours |
| `K_AB` | Session key between Alice and Bob | A few minutes per ticket |
| `TGT` | Ticket-Granting Ticket = `K_TGS(A, K_S,tgs, t_start, t_exp)` | Hours |
| `ticket_B` | Service ticket = `K_B(A, K_AB, t_start, t_exp)` | A few minutes |
| `Auth` | Authenticator = `K_S,tgs(A, t_req)` | Single-use |

The two envelopes (`TGT` sealed under `K_TGS`, `ticket_B` sealed under `K_B`) are exactly Needham-Schroeder's tickets. Kerberos adds timestamps inside both and a separate Authenticator under the freshly issued session key.

### Why timestamps replace nonces

Needham-Schroeder 1978 needed a round-trip nonce to prove freshness because clocks could not be trusted to be synchronized. By 1988, RFC 1305 (NTP) was already a year old, and the MIT environment had NTP everywhere. Kerberos designers decided to require clock sync and use timestamps for freshness: a packet whose timestamp is more than `clockskew` minutes off from server time is rejected. The tradeoff is that if NTP fails (or an attacker manipulates it), Kerberos fails closed. The 5-minute default skew is a balance: tight enough to limit replay windows, loose enough to tolerate real-world NTP jitter.

The `t_req - 1` in the optional AP-REP (message 6) is the analog of Needham-Schroeder's `R - 1` confirmation: Bob proves he can use `K_AB` by transforming the timestamp Alice sent, exactly the way NS proved freshness by responding to `R_A2 - 1`.

### Pre-authentication and PKINIT

RFC 4120 had a flaw: the AS-REQ was in plaintext with the username. An attacker could harvest valid usernames by spraying requests and looking at the AS-REP error codes. The fix was pre-authentication data (PA-ETYPE-INFO2) in RFC 4120 §3.1.1.4, and later PKINIT (RFC 4556) lets the client send a PKCS#7 signed X.509 certificate instead of a password hash. PKINIT is the foundation for smart-card login to Active Directory.

### Cross-realm authentication

When Alice in realm `EXAMPLE.COM` needs a service in `PARTNER.ORG`, she asks her TGS for a referral ticket — a TGT-like envelope that the foreign realm's TGS can decrypt. The foreign TGS must have registered a `krbtgt/PARTNER.ORG@EXAMPLE.COM` principal; without that pre-registration, no cross-realm tickets exist. Modern deployments use `krbtgt` rotation policies (the 2018 "Golden Ticket" attacks showed that a long-lived `krbtgt` key is a single point of compromise).

## Build It

### Step 1 — String-to-key from a password

```python
from main import string_to_key

k_a = string_to_key("correct horse battery staple", salt=b"alice@EXAMPLE.COM", iterations=4096)
```

Implements PBKDF2-HMAC-SHA256 (RFC 2898 §5.2). Real Kerberos uses the enctype-specific `string-to-key` defined in RFC 3961 §6, but PBKDF2 with a 16-byte salt and 4096 rounds is the equivalent for our teaching cipher.

### Step 2 — Build the six-message exchange

```python
from main import KerberosRealm, run_kerberos_login

realm = KerberosRealm(name="EXAMPLE.COM")
realm.register_user("alice", "correct horse battery staple")
realm.register_service("bob", "fileserver")

result = run_kerberos_login(realm, "alice", "correct horse battery staple", "bob")
print(result.service_session_key.hex())
```

The simulator runs AS-REQ → AS-REP → TGS-REQ → TGS-REP → AP-REQ → AP-REP, returns the session key `K_AB`, and the timestamps of every step.

### Step 3 — Reject a bad password

```python
result = run_kerberos_login(realm, "alice", "WRONG", "bob")
assert result.error == "KDC_ERR_PREAUTH_FAILED"
```

The AS checks the pre-authentication data (`K_A(t_req)`) and refuses to issue a TGT if it does not decrypt under the password-derived key.

### Step 4 — Reject a stale ticket

```python
import time
result = run_kerberos_login(realm, "alice", "correct horse battery staple", "bob", now=time.time() + 600)
assert "KRB_AP_ERR_SKEW" in result.error
```

A 10-minute clock skew on Alice's clock pushes her `t_req` outside the 5-minute tolerance. The AS rejects before even sending the TGT.

### Step 5 — Cross-realm

```python
partner_realm = KerberosRealm(name="PARTNER.ORG")
partner_realm.register_service("bob", "fileserver")
realm.add_trust("PARTNER.ORG", partner_realm.tgs_key)
result = run_kerberos_login(realm, "alice", "...", "bob@PARTNER.ORG")
```

The TGS in `EXAMPLE.COM` issues a referral ticket to `PARTNER.ORG`'s TGS, which then mints a service ticket for the cross-realm `bob`.

## Use It

| Real system | Architecture | Difference from our lab |
|---|---|---|
| MIT Kerberos (krb5) | KDC = `krb5kdc` + `kadmind`; tickets are ASN.1 `EncKDCRepPart` | Uses AES-256-CTS-HMAC-SHA1-96 (RFC 3961) instead of our toy cipher |
| Microsoft Active Directory | KDC embedded in domain controllers; uses Kerberos + NTLM fallback | AD adds SPNEGO, S4U2Self/S4U2Proxy (constrained delegation), and Kerberos armoring |
| Apple Open Directory | KDC + LDAP directory; macOS-native GSSAPI | Same protocol; uses ECDH for fast armoring |
| Hadoop RPC | SASL/GSSAPI-Kerberos over TCP | Tokens carry Hadoop-specific authorization data |
| SSH with GSSAPI | Kerberos as the SSH auth method | RFC 4462 wraps AP-REQ in SSH userauth |
| OAuth 2.0 / OIDC | Authorization server (TGS analog), bearer tokens | Not Kerberos; tickets are JSON Web Tokens, not ASN.1 |
| SAML 2.0 | IdP issues signed assertions | Closest analog to cross-realm; XML signature instead of Kerberos envelopes |

## Ship It

The reusable artifact in `outputs/prompt-kerberos-lab.md` is a small `kerberos_sim.py` that exposes:

- `KerberosRealm(name)` with `register_user`, `register_service`, `add_trust`.
- `run_kerberos_login(realm, user, password, service, now=None, clockskew=300)`.
- `KerberosResult` dataclass: `service_session_key`, `error`, `messages`, `tickets`.
- A `cli.py` that takes username, password, and service name from argv and prints the full message log plus the session key fingerprint.

## Exercises

1. Trace what happens if Alice's workstation computes `K_A` from a *wrong* password. Which message first reveals the failure, and what error code does the AS return? Compare with the 1978 Needham-Schroeder version, where Alice only learns the auth failed at message 5.
2. Set `clockskew=0` and `now=time.time()+1`. Every timestamp is slightly off. How many message rejections occur? At what layer does the protocol become unusable?
3. Pre-authentication (RFC 4120 §3.1.1.4): Alice sends `PA-ENC-TIMESTAMP` (`K_A(now)`) in the AS-REQ. What attack does this prevent compared to the original plaintext AS-REQ?
4. PKINIT (RFC 4556): replace the password-derived `K_A` with a private RSA key. What is sent in the AS-REQ, and what does the AS verify? Why is this better than smart-card-only solutions?
5. Cross-realm: trace the indirection. How many round trips does Alice need to fetch a ticket from a foreign realm? Where does the latency come from?
6. Replay an AP-REQ from yesterday. The service ticket is still cryptographically valid (the HMAC is intact) but `t_req` is stale. Which field of the ticket envelope protects against the replay?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| KDC | "the auth server" | Two halves: Authentication Server (AS) verifies identities; Ticket-Granting Server (TGS) mints service tickets |
| TGT | "the login ticket" | `K_TGS(A, K_S,tgs, t_exp)`; reusable for ~10 hours to ask for service tickets |
| Service ticket | "the resource ticket" | `K_B(A, K_AB, t_exp)`; proves Alice is authorized to use Bob |
| Authenticator | "the fresh proof" | `K_S,tgs(A, t_req)`; single-use timestamp under the session key |
| Realm | "the domain" | Administrative boundary; one realm = one KDC and one user namespace |
| Principal | "the name" | `name/instance@REALM`; e.g., `alice@EXAMPLE.COM`, `krbtgt/EXAMPLE.COM@EXAMPLE.COM` |
| krbtgt | "the TGS key" | Special principal whose key is the TGS long-term key; rotation is critical for security |
| String-to-key | "the password hash" | PBKDF2 (RFC 2898) or enctype-specific (RFC 3961) derivation from password + salt |
| Pre-auth | "PA-ENC-TS" | `K_A(timestamp)` in the AS-REQ; prevents offline username enumeration |
| Clock skew | "the tolerance" | RFC 4120 §3.1.3 default 300 seconds; packets outside this window are rejected |

## Further Reading

- RFC 4120 — The Kerberos Network Authentication Service (V5), Steiner, Neuman, Schiller
- RFC 4556 — Public Key Cryptography for Initial Authentication in Kerberos (PKINIT)
- RFC 3961 — Encryption and Checksum Specifications for Kerberos 5 (enctype family)
- RFC 3962 — Advanced Encryption Standard (AES) Encryption for Kerberos 5
- RFC 6253 — Hostnames in Kerberos Realm Names
- MIT Kerberos Consortium documentation (`web.mit.edu/kerberos`)
- Neuman, C., & Ts'o, T. — *Kerberos: An Authentication Service for Computer Networks*, IEEE Communications Magazine, 1994
- Microsoft Kerberos documentation (Active Directory authentication)
- Project Athena — *Kerberos: An Authentication Service for Open Network Systems*, 1988
