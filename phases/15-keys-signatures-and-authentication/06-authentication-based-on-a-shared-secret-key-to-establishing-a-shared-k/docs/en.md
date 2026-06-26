# Authentication Based on a Shared Secret Key to Establishing a Shared Key the Diffie-hellman Key Exchange

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Build
**Languages:** Python, protocol traces
**Prerequisites:** Earlier lessons in Phase 15
**Time:** ~90 minutes

## Learning Objectives
- Explain source section 8.7.1 in operational terms
- Explain source section 8.7.2 in operational terms
- Identify the packet fields, timers, counters, state, or logs that prove the behavior
- Connect the concept to at least one realistic failure mode
- Produce a reusable trace annotation, runbook, diagram, script, or prompt

## The Problem
Authentication Based on a Shared Secret Key to Establishing a Shared Key the Diffie-hellman Key Exchange matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.

This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.

## The Concept

Source material: [`chapters/chapter-08-network-security.md`](../../../../chapters/chapter-08-network-security.md) sections `8.7.1`, `8.7.2`.

For our first authentication protocol, we will assume that Alice and Bob al-
ready share a secret key, K . This shared key might have been agreed upon on
AB
the telephone or in person, but, in any event, not on the (insecure) network.
This protocol is based on a principle found in many authentication protocols:
one party sends a random number to the other, who then transforms it in a special
way and returns the result. Such protocols are called challenge-response proto-
cols. In this and subsequent authentication protocols, the following notation will
be used:
A, B are the identities of Alice and Bob.
R 's are the challenges, where i identifies the challenger.

K 's are keys, where i indicates the owner.

K is the session key.

---

<a id="page-841"></a>

<!-- Page 841 of 888 -->

SEC. 8.7 AUTHENTICATION PROTOCOLS 829
The message sequence for our first shared-key authentication protocol is illus-
trated in Fig. 8-32. In message 1, Alice sends her identity, A, to Bob in a way that
Bob understands. Bob, of course, has no way of knowing whether this message
came from Alice or from Trudy, so he chooses a challenge, a large random num-
ber, R , and sends it back to ''Alice'' as message 2, in plaintext. Alice then en-
crypts the message with the key she shares with Bob and sends the ciphertext back in message 3.

### Working Model

```text
user-visible symptom
        |
        v
network mechanism: Authentication Based on a Shared Secret Key to Establishing a Shared Key the Diffie-hellman Key Exchange
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

Start with [`outputs/prompt-authentication-based-on-a-shared-secret-key-to-establishing-a-shared-k.md`](../outputs/prompt-authentication-based-on-a-shared-secret-key-to-establishing-a-shared-k.md).

## Exercises

1. List the source rules or assumptions that matter most for this topic.
2. Capture or sketch one normal trace and annotate the important fields.
3. Describe one realistic failure and the evidence you would collect first.
4. Compare this mechanism with the layer directly above or below it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Authentication Based on a Shared Secret Key to Establishing a Shared Key the Diffie-hellman Key Exchange | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |
| Section 8.7.1 | A book subsection | The authoritative source slice for this lesson |
| Artifact | Homework output | A reusable operational tool you can apply later |

## Further Reading

- The full source chapter linked above
- Relevant RFCs or standards named in the source section
- Wireshark display filter reference for packet evidence
