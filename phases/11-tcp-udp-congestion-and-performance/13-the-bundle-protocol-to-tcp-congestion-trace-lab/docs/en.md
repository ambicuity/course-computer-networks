# The Bundle Protocol to TCP Congestion Trace Lab

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Earlier lessons in Phase 11
**Time:** ~90 minutes

## Learning Objectives
- Explain source section 6.7.2 in operational terms
- Identify the packet fields, timers, counters, state, or logs that prove the behavior
- Connect the concept to at least one realistic failure mode
- Produce a reusable trace annotation, runbook, diagram, script, or prompt

## The Problem
The Bundle Protocol to TCP Congestion Trace Lab matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.

This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.

## The Concept

Source material: `chapters/chapter-06-the-transport-layer.md` section `6.7.2`.

To take a closer look at the operation of DTNs, we will now look at the IETF
protocols. DTNs are an emerging kind of network, and experimental DTNs have
used different protocols, as there is no requirement that the IETF protocols be
used. However, they are at least a good place to start and highlight many of the
key issues.
The DTN protocol stack is shown in Fig. 6-58. The key protocol is the Bun-
dle protocol, which is specified in RFC 5050. It is responsible for accepting mes-
sages from the application and sending them as one or more bundles via store-
carry-forward operations to the destination DTN node. It is also apparent from
Fig. 6-58 that the Bundle protocol runs above the level of TCP/IP. In other words,
TCP/IP may be used over each contact to move bundles between DTN nodes.
This positioning raises the issue of whether the Bundle protocol is a transport
layer protocol or an application layer protocol. Just as with RTP, we take the
position that, despite running over a transport protocol, the Bundle protocol is pro-
viding a transport service to many different applications, and so we cover DTNs
in this chapter.

### Working Model

```text
user-visible symptom
        |
        v
network mechanism: The Bundle Protocol to TCP Congestion Trace Lab
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

Start with [`outputs/prompt-the-bundle-protocol-to-tcp-congestion-trace-lab.md`](../outputs/prompt-the-bundle-protocol-to-tcp-congestion-trace-lab.md).

## Exercises

1. List the source rules or assumptions that matter most for this topic.
2. Capture or sketch one normal trace and annotate the important fields.
3. Describe one realistic failure and the evidence you would collect first.
4. Compare this mechanism with the layer directly above or below it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| The Bundle Protocol to TCP Congestion Trace Lab | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |
| Section 6.7.2 | A book subsection | The authoritative source slice for this lesson |
| Artifact | Homework output | A reusable operational tool you can apply later |

## Further Reading

- The full source chapter linked above
- Relevant RFCs or standards named in the source section
- Wireshark display filter reference for packet evidence
