# Kerberos V5: AS, TGS, service tickets, and the realm of trust

> Kerberos is a trusted-third-party authentication protocol designed at MIT in 1988 and standardized as RFC 4120 (Kerberos V5) in 2005. It authenticates users and services across an untrusted network by handing out short-lived, encrypted tickets from a central authority. The protocol has three parties: the client C (Alice), the service S (Bob's file server), and the Key Distribution Center KDC, which contains an Authentication Service (AS) and a Ticket Granting Service (TGS). The three-message flow is: (1) C -> AS: "I am Alice, give me a TGT" using Alice's password-derived key; (2) AS -> C: TGT encrypted under K_TGS plus a session key for C-to-TGS encrypted under K_C; (3) C -> TGS: "I want a ticket for S" using the session key. The TGS then issues a service ticket encrypted under K_S, which C presents to S. Every ticket has a lifetime (typically 8-24 hours) and an authenticator that includes a fresh timestamp to defeat replays. Kerberos V5 added several improvements over V4: longer ticket lifetimes, ASN.1 encoding, preauthentication to defeat offline dictionary attacks, and a network of cross-realm trust via referral tickets.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 14 lessons 01-09, Chapter 8.5
**Time:** ~80 minutes

## Learning Objectives

- Trace the four-message Kerberos V5 authentication flow: AS-REQ, AS-REP, TGS-REQ, TGS-REP, and identify the role of each ticket (TGT, service ticket).
- Explain why the AS issues a TGT encrypted under K_TGS rather than under the service's key, and how the TGT lets the client request service tickets without re-entering a password.
- Implement ticket encoding as signed JSON blobs using HMAC-SHA256, with separate keys for C, TGS, and S, and verify decryption + verification at each step.
- Construct a replay attack by capturing an old service ticket and replaying it, and demonstrate that the timestamp inside the authenticator plus the S-side replay cache defeats it.
- Identify three real-world Kerberos deployments (MIT Kerberos, Microsoft Active Directory, Heimdal) and explain how Active Directory extends Kerberos with PAC and SPNEGO.

## The Problem

An enterprise has 5,000 employees and 200 file servers. Each user needs to authenticate to multiple servers per day. Distributing a separate symmetric key for every (user, server) pair is 5,000 × 200 = 1,000,000 keys to manage; storing them on every laptop is a nightmare. Building a public-key infrastructure (PKI) avoids the key-volume problem but does not give single sign-on: every login requires the user to type a private-key passphrase. What the enterprise wants is single sign-on: type the password once per workday, and authenticate to every service without further password prompts.

Kerberos solves this by introducing a trusted third party, the Key Distribution Center (KDC), that hands out short-lived tickets encrypted under per-service keys. The user's password is used once at login to decrypt a session key from the AS; from then on, the session key authenticates the user to every service via ticket-granting tickets. Tickets expire (default 24 hours, often 8 hours in practice) so a stolen laptop has a bounded exposure window.

## The Concept

Source: chapters/chapter-08-network-security.md, section 8.5 (Authentication Using Kerberos). The companion diagram is assets/kerberos-v5-authentication.svg.

### The KDC and its two halves

The KDC is logically two services running on one or more replicated hosts:
- Authentication Service (AS): verifies the user's identity (typically by decrypting a request with K_C, the user's password-derived key) and issues a Ticket Granting Ticket (TGT).
- Ticket Granting Service (TGS): accepts a TGT, verifies it, and issues service tickets for specific servers.

The KDC holds a database of every principal's long-term key: K_C for client, K_S for each service, and K_TGS for itself. In production this database is the Kerberos principal database; in Active Directory it is the AD account database.

### The four-message flow (V5 with preauth)

| Step | From | To | Wire | Encrypted under | What |
|------|------|----|------|------|------|
| 1 | C | AS | AS-REQ (C, TGS, n1) | -- (cleartext) | Client requests a TGT for the TGS |
| 1.5 | C | AS | preauth: timestamp encrypted under K_C | K_C | Proves C knows the password (V5 addition) |
| 2 | AS | C | K_C(K_C-TGS, n1) + TGS(C, K_C-TGS, ltime) | K_C and K_TGS | AS returns the session key K_C-TGS plus the TGT |
| 3 | C | TGS | TGS-REQ: TGT + K_C-TGS(S, n2, t_C) | K_TGS and K_C-TGS | Client presents TGT and an authenticator for S |
| 4 | TGS | C | K_C-TGS(K_C-S, n2) + S(C, K_C-S, ltime) | K_C-TGS and K_S | TGS returns a service session key plus a service ticket |
| 5 | C | S | AP-REQ: S(C, K_C-S, ltime) + K_C-S(t_C) | K_S and K_C-S | Client presents service ticket and authenticator |
| 6 | S | C | AP-REP: K_C-S(t_S) | K_C-S | Optional mutual authentication |

The actual count is six messages (or four if preauth is folded in), and the canonical Kerberos diagram is the centerpiece of Chapter 8. The two-layer structure (TGT then service ticket) is what makes single sign-on work: the user authenticates once to the AS, and the TGT is reused for every service ticket.

### Tickets and authenticators

A ticket has three parts: the client id C, the session key for client-service communication (K_C-S), and the lifetime (ltime). The ticket is encrypted under the receiver's long-term key: TGTs under K_TGS, service tickets under K_S. The receiver decrypts and verifies the lifetime.

An authenticator is the client's proof-of-possession: K_C-S(C, t_C) — the client id and a fresh timestamp t_C, encrypted under the service session key K_C-S. The service checks that the timestamp is within Δ of its own clock (typically 5 minutes), and that it has not seen this exact (C, t_C) pair recently (replay cache). The authenticator is the per-message proof; the ticket is the per-session proof.

### Why preauthentication (V5)

V4 was vulnerable to offline dictionary attack: Trudy could request AS-REQ with any username and the AS would return a TGT encrypted under K_C (which is KDF(password)). Trudy could then guess passwords and test decryption offline. V5 added a preauth step where the client must encrypt a timestamp under K_C, proving it knows the password before the AS returns anything useful.

### Cross-realm trust

Kerberos V5 supports transitive trust via referral tickets. If realm A trusts realm B, and B trusts realm C, then a client in A can request a referral ticket to C through B. The TGS in B issues a referral ticket encrypted under a cross-realm key (A, B) that C presents to a TGS in B to obtain a service ticket for a service in C. This is how MIT Kerberos federates across universities and how Active Directory domains form a forest.

### Where Kerberos is used in practice

- MIT Kerberos: the reference implementation, used in Unix/Linux authentication.
- Microsoft Active Directory: the dominant enterprise deployment. AD extends Kerberos V5 with the Privilege Attribute Certificate (PAC), SPNEGO for HTTP, and KDC proxy via the MS-KKDCP protocol.
- Heimdal: a free Kerberos implementation common in BSD systems.
- SSH GSSAPI: SSH can authenticate using Kerberos tickets instead of public keys.

## Build It

code/main.py implements a simplified Kerberos V5 flow. Work through it in this order:

1. Run python3 main.py and read the import block. The simulator uses hmac for ticket signing and secrets for nonce generation.
2. Read Principal: each principal has a long-term HMAC key derived from a password (or pre-shared secret). K_C, K_TGS, K_S are all 32-byte HMAC keys.
3. Read KDC.__init__: the KDC holds the database of all keys (K_C, K_TGS, K_S).
4. Read as_exchange: client sends AS-REQ; KDC validates preauth (encrypted timestamp under K_C), then issues a TGT and a session key K_C-TGS.
5. Read tgs_exchange: client sends TGS-REQ with TGT plus authenticator; TGS validates the TGT and authenticator; KDC issues a service ticket and a session key K_C-S.
6. Read ap_exchange: client presents service ticket + authenticator to S; S validates and optionally returns AP-REP for mutual auth.
7. Read scenario_replay: replay an old AP-REQ; S's replay cache catches it.
8. Run the main() scenarios: honest AS+TGS+AP flow, replay attack blocked.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Issue a TGT | AS-REQ + preauth returns a TGT encrypted under K_TGS and K_C-TGS | Client can decrypt K_C-TGS with K_C; TGS can decrypt the TGT with K_TGS |
| Issue a service ticket | TGS-REQ returns K_C-S and service ticket | Client decrypts with K_C-TGS; S decrypts ticket with K_S |
| Authenticate to S | AP-REQ with timestamp authenticator | S validates the ticket, the authenticator's freshness, and the replay cache |
| Defeat replay | Same AP-REQ submitted twice | First accepted, second rejected with "replay detected" |
| Mutual authentication | S returns AP-REP encrypted under K_C-S | Client validates t_S is within Δ of its clock |

## Ship It

Produce one artifact under outputs/:

- A one-page runbook titled "How single sign-on works in Active Directory" that walks the four-step Kerberos V5 exchange and identifies which step corresponds to which AD event log entry (4769 = TGS ticket, 4768 = TGT issued).
- Or a threat-model document listing what an attacker who steals a TGT can and cannot do: cannot use the TGT without K_C-TGS (encrypted under K_C); can use the TGT until it expires; can request service tickets for any service in the realm.

Start from outputs/prompt-kerberos-v5-authentication.md and back every claim with a transcript from code/main.py.

## Exercises

1. Trace the four-step exchange for "Alice wants to access fileserver.example.com." Identify the message in which K_C-S is first created, and the message in which the service ticket is decrypted.
2. A user has logged out and logged back in 30 minutes later. Describe what happens at the AS in the second login. Why is the preauth step crucial?
3. Modify code/main.py to simulate a stolen-laptop attack: Trudy captures the TGT from disk and uses it from her own machine. Show that she can request service tickets until the TGT expires, and that she cannot decrypt K_C-TGS because she does not know Alice's password.
4. Add a 30-second timestamp skew window to S's authenticator check. Show that an AP-REQ with timestamp t_C 60 seconds in the past is rejected.
5. Compare Kerberos V4 and V5 in three properties: ticket format (V4 uses a binary format, V5 uses ASN.1), preauth (V4 had none, V5 added encrypted-timestamp), and ticket lifetime (V4 max ~21 hours, V5 max unlimited). Identify one security improvement in V5 that comes from each.
6. Active Directory extends Kerberos V5 with the Privilege Attribute Certificate (PAC), which carries authorization info (group membership, SID) inside the service ticket. Explain why this is a security win (the authz info is signed by the KDC) and a performance risk (PACs can be megabytes for users in many groups).

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| KDC | key distribution center | Trusted third party that issues TGTs and service tickets; holds the principal database |
| AS | authentication service | First half of the KDC; verifies user identity and issues TGTs |
| TGS | ticket granting service | Second half of the KDC; accepts a TGT and issues service tickets |
| TGT | ticket granting ticket | Encrypted under K_TGS; reusable across many service-ticket requests |
| Service ticket | the per-server ticket | Encrypted under K_S; proves the client holds K_C-S |
| Authenticator | the freshness proof | K_C-S(C, t_C) — a per-message freshness proof inside the ticket |
| Principal | user or service | The unit of identity in Kerberos; principal name is user@REALM |
| Realm | the trust domain | An administrative domain; cross-realm trust is transitive |
| Preauth | V5's dictionary defense | Client encrypts a timestamp under K_C to prove knowledge of the password |
| PAC | Active Directory extension | Privilege Attribute Certificate; carries authz info inside the ticket |
| SPNEGO | HTTP Kerberos | Simple and Protected GSSAPI Negotiation; HTTP's Kerberos wrapper |
| KDC AS-REQ/TGS-REQ | the wire messages | The two request types sent by the client to the KDC |

## Further Reading

- RFC 4120 — The Kerberos Network Authentication Service (V5). The canonical protocol specification.
- RFC 4556 — Public Key Cryptography for Initial Authentication in Kerberos (PKINIT).
- RFC 4757 — The RC4-HMAC Kerberos Encryption Types Used by Microsoft Windows.
- RFC 6806 — Kerberos Principal Name Canonicalization and Cross-Realm Referrals.
- Neuman, C., and Ts'o, T. (1994). "Kerberos: An Authentication Service for Computer Networks." IEEE Communications 32(9): 33-38.
- MIT Kerberos documentation — web.mit.edu/kerberos.
- Microsoft MS-KILE — Kerberos Protocol Extensions.
- Tanenbaum & Wetherall, Computer Networks, Chapter 8 Section 8.5.