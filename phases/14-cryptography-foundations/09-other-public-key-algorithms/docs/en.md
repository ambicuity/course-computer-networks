# Other Public-key Algorithms

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Earlier lessons in Phase 14
**Time:** ~90 minutes

## Learning Objectives
- Explain source section 8.3.2 in operational terms
- Identify the packet fields, timers, counters, state, or logs that prove the behavior
- Connect the concept to at least one realistic failure mode
- Produce a reusable trace annotation, runbook, diagram, script, or prompt

## The Problem
Other Public-key Algorithms matters because network failures usually appear as vague symptoms: delay, loss, unreachable services, broken names, failed handshakes, or inconsistent application behavior. The engineer has to reduce that symptom to layer-specific evidence.

This lesson keeps the AI Engineering course rhythm but applies it to networking: understand the source, build or inspect a concrete model, use real tools, and ship an artifact that makes the idea reusable.

## The Concept

Source material: `chapters/chapter-08-network-security.md` section `8.3.2`.

Although RSA is widely used, it is by no means the only public-key algorithm
known. The first public-key algorithm was the knapsack algorithm (Merkle and
Hellman, 1978). The idea here is that someone owns a large number of objects,
each with a different weight. The owner encodes the message by secretly select-
ing a subset of the objects and placing them in the knapsack. The total weight of
the objects in the knapsack is made public, as is the list of all possible objects and
their corresponding weights. The list of objects in the knapsack is kept secret.
With certain additional restrictions, the problem of figuring out a possible list of
objects with the given weight was thought to be computationally infeasible and
formed the basis of the public-key algorithm.

---

<a id="page-809"></a>

<!-- Page 809 of 888 -->

SEC. 8.3 PUBLIC-KEY ALGORITHMS 797
The algorithm's inventor, Ralph Merkle, was quite sure that this algorithm
could not be broken, so he offered a $100 reward to anyone who could break it.
Adi Shamir (the ''S'' in RSA) promptly broke it and collected the reward.
Undeterred, Merkle strengthened the algorithm and offered a $1000 reward to
anyone who could break the new one. Ronald Rivest (the ''R'' in RSA) promptly broke the new one and collected the reward.

### Working Model

```text
user-visible symptom
        |
        v
network mechanism: Other Public-key Algorithms
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

Start with [`outputs/prompt-other-public-key-algorithms.md`](../outputs/prompt-other-public-key-algorithms.md).

## Exercises

1. List the source rules or assumptions that matter most for this topic.
2. Capture or sketch one normal trace and annotate the important fields.
3. Describe one realistic failure and the evidence you would collect first.
4. Compare this mechanism with the layer directly above or below it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Other Public-key Algorithms | A chapter topic to memorize | A mechanism that should leave observable evidence in packets, state, counters, or logs |
| Section 8.3.2 | A book subsection | The authoritative source slice for this lesson |
| Artifact | Homework output | A reusable operational tool you can apply later |

## Further Reading

- The full source chapter linked above
- Relevant RFCs or standards named in the source section
- Wireshark display filter reference for packet evidence
