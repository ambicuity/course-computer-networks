# Cryptanalysis to RSA

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Earlier lessons in Phase 14
**Time:** ~90 minutes

## Learning Objectives
- Explain source section 8.2.5 in operational terms
- Explain source section 8.3.1 in operational terms
- Identify the packet fields, timers, counters, state, or logs that prove the behavior
- Connect the concept to at least one realistic failure mode
- Produce a reusable trace annotation, runbook, diagram, script, or prompt

## The Problem
Cryptanalysis to RSA matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.

This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.

## The Concept

Source material: [`chapters/chapter-08-network-security.md`](../../../../chapters/chapter-08-network-security.md) sections `8.2.5`, `8.3.1`.

Before leaving the subject of symmetric-key cryptography, it is worth at least
mentioning four developments in cryptanalysis. The first development is dif-
ferential cryptanalysis (Biham and Shamir, 1997). This technique can be used
to attack any block cipher.

---

<a id="page-805"></a>

<!-- Page 805 of 888 -->

SEC. 8.2 SYMMETRIC-KEY ALGORITHMS 793
to attack any block cipher. It works by beginning with a pair of plaintext blocks
differing in only a small number of bits and watching carefully what happens on
each internal iteration as the encryption proceeds. In many cases, some bit pat-
terns are more common than others, which can lead to probabilistic attacks.
The second development worth noting is linear cryptanalysis (Matsui, 1994).
It can break DES with only 243 known plaintexts. It works by XORing certain
bits in the plaintext and ciphertext together and examining the result. When done
repeatedly, half the bits should be 0s and half should be 1s. Often, however,
ciphers introduce a bias in one direction or the other, and this bias, however small,
can be exploited to reduce the work factor. For the details, see Matsui's paper.
The third development is using analysis of electrical power consumption to
find secret keys.

### Working Model

```text
user-visible symptom
        |
        v
network mechanism: Cryptanalysis to RSA
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

Start with [`outputs/prompt-cryptanalysis-to-rsa.md`](../outputs/prompt-cryptanalysis-to-rsa.md).

## Exercises

1. List the source rules or assumptions that matter most for this topic.
2. Capture or sketch one normal trace and annotate the important fields.
3. Describe one realistic failure and the evidence you would collect first.
4. Compare this mechanism with the layer directly above or below it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Cryptanalysis to RSA | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |
| Section 8.2.5 | A book subsection | The authoritative source slice for this lesson |
| Artifact | Homework output | A reusable operational tool you can apply later |

## Further Reading

- The full source chapter linked above
- Relevant RFCs or standards named in the source section
- Wireshark display filter reference for packet evidence
