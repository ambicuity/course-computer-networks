# Protocols for Long Fat Networks to DTN Architecture

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Earlier lessons in Phase 11
**Time:** ~90 minutes

## Learning Objectives
- Explain source section 6.6.6 in operational terms
- Explain source section 6.7.1 in operational terms
- Identify the packet fields, timers, counters, state, or logs that prove the behavior
- Connect the concept to at least one realistic failure mode
- Produce a reusable trace annotation, runbook, diagram, script, or prompt

## The Problem
Protocols for Long Fat Networks to DTN Architecture matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.

This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.

## The Concept

Source material: `chapters/chapter-06-the-transport-layer.md` sections `6.6.6`, `6.7.1`.

Since the 1990s, there have been gigabit networks that transmit data over
large distances. Because of the combination of a fast network, or ''fat pipe,'' and
long delay, these networks are called long fat networks. When these networks
arose, people's first reaction was to use the existing protocols on them, but vari-
ous problems quickly arose. In this section, we will discuss some of the problems
with scaling up the speed and delay of network protocols.
The first problem is that many protocols use 32-bit sequence numbers. When
the Internet began, the lines between routers were mostly 56-kbps leased lines, so
a host blasting away at full speed took over 1 week to cycle through the sequence
numbers. To the TCP designers, 232 was a pretty decent approximation of infinity
because there was little danger of old packets still being around a week after they
were transmitted. With 10-Mbps Ethernet, the wrap time became 57 minutes,
much shorter, but still manageable. With a 1-Gbps Ethernet pouring data out onto
the Internet, the wrap time is about 34 seconds, well under the 120-sec maximum
packet lifetime on the Internet. All of a sudden, 232 is not nearly as good an
approximation to infinity since a fast sender can cycle through the sequence space
while old packets still exist.

### Working Model

```text
user-visible symptom
        |
        v
network mechanism: Protocols for Long Fat Networks to DTN Architecture
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

Start with [`outputs/prompt-protocols-for-long-fat-networks-to-dtn-architecture.md`](../outputs/prompt-protocols-for-long-fat-networks-to-dtn-architecture.md).

## Exercises

1. List the source rules or assumptions that matter most for this topic.
2. Capture or sketch one normal trace and annotate the important fields.
3. Describe one realistic failure and the evidence you would collect first.
4. Compare this mechanism with the layer directly above or below it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Protocols for Long Fat Networks to DTN Architecture | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |
| Section 6.6.6 | A book subsection | The authoritative source slice for this lesson |
| Artifact | Homework output | A reusable operational tool you can apply later |

## Further Reading

- The full source chapter linked above
- Relevant RFCs or standards named in the source section
- Wireshark display filter reference for packet evidence
