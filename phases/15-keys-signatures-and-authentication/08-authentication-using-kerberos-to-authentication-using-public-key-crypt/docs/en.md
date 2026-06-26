# Authentication Using Kerberos to Authentication Using Public-key Cryptography

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Build
**Languages:** Python, protocol traces
**Prerequisites:** Earlier lessons in Phase 15
**Time:** ~90 minutes

## Learning Objectives
- Explain source section 8.7.4 in operational terms
- Explain source section 8.7.5 in operational terms
- Identify the packet fields, timers, counters, state, or logs that prove the behavior
- Connect the concept to at least one realistic failure mode
- Produce a reusable trace annotation, runbook, diagram, script, or prompt

## The Problem
Authentication Using Kerberos to Authentication Using Public-key Cryptography matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.

This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.

## The Concept

Source material: `chapters/chapter-08-network-security.md` sections `8.7.4`, `8.7.5`.

An authentication protocol used in many real systems (including Windows
2000 and later versions) is Kerberos, which is based on a variant of Needham-
Schroeder. It is named for a multiheaded dog in Greek mythology that used to
guard the entrance to Hades (presumably to keep undesirables out). Kerberos was
designed at M.I.T. to allow workstation users to access network resources in a
secure way. Its biggest difference from Needham-Schroeder is its assumption that
all clocks are fairly well synchronized. The protocol has gone through several
iterations. V5 is the one that is widely used in industry and defined in RFC 4120.
The earlier version, V4, was finally retired after serious flaws were found (Yu et
al., 2004). V5 improves on V4 with many small changes to the protocol and some
improved features, such as the fact that it no longer relies on the now-dated DES.
For more information, see Neuman and Ts'o (1994).
Kerberos involves three servers in addition to Alice (a client workstation):
1. Authentication Server (AS): Verifies users during login.
2. Ticket-Granting Server (TGS): Issues ''proof of identity tickets.''
3. Bob the server: Actually does the work Alice wants performed.

--

### Working Model

```text
user-visible symptom
        |
        v
network mechanism: Authentication Using Kerberos to Authentication Using Public-key Cryptography
        |
        v
observable evidence: packet fields, counters, timers, logs, or state
        |
        v
engineering decision: explain, tune, reroute, retry, secure, or redesign
```

## Build It

1. Write the one-paragraph mechanism summary in your own words.
2. Draw the packet flow, state machine, queue, address mapping, or trust boundary.
3. Identify the exact evidence that would confirm normal behavior.
4. Identify one failure mode and the smallest test that would confirm or reject it.
5. Run or adapt `code/main.py` when present, then replace sample observations with your own evidence.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | Packet headers, protocol messages, counters | You can explain why this is not merely an application symptom |
| Explain normal behavior | Source rules plus a clean trace or diagram | Observed fields and state transitions match the model |
| Diagnose abnormal behavior | Before/after traces, timing, errors | The failure hypothesis predicts the evidence |

## Ship It

Create one artifact under `outputs/`:

- A trace annotation checklist
- A one-page failure-mode runbook
- A protocol/state diagram
- A small parser, calculator, simulator, or diagnostic script
- A study prompt that teaches the topic from evidence

Start with [`outputs/prompt-authentication-using-kerberos-to-authentication-using-public-key-crypt.md`](../outputs/prompt-authentication-using-kerberos-to-authentication-using-public-key-crypt.md).

## Exercises

1. List the source rules or assumptions that matter most for this topic.
2. Capture or sketch one normal trace and annotate the important fields.
3. Describe one realistic failure and the evidence you would collect first.
4. Compare this mechanism with the layer directly above or below it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Authentication Using Kerberos to Authentication Using Public-key Cryptography | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |
| Section 8.7.4 | A book subsection | The authoritative source slice for this lesson |
| Artifact | Homework output | A reusable operational tool you can apply later |

## Further Reading

- The full source chapter linked above
- Relevant RFCs or standards named in the source section
- Wireshark display filter reference for packet evidence
