# Multilayer Incident Postmortem from Traffic and Logs

> You are handed a packet capture, syslog logs, application logs, and BGP updates from a 45-minute outage. Correlate evidence across all layers, identify the root cause, and write a production-grade postmortem.

**Type:** Capstone
**Languages:** Python, Wireshark, shell
**Prerequisites:** Phase 17 integrated troubleshooting labs; understanding of layered debugging and evidence correlation
**Time:** ~160 minutes

## Learning Objectives

- Correlate evidence from packet captures, syslog, application logs, and routing updates across the OSI layers
- Build a timeline of events from multiple evidence sources, aligning timestamps and identifying causal chains
- Identify the root cause from a multilayer symptom cascade: DNS failure -> connection resets -> BGP withdrawal -> application timeout
- Implement automated evidence correlation: match timestamps across log sources, identify co-occurring events
- Distinguish root cause from contributing factors and cascading symptoms
- Produce a production-grade postmortem document with timeline, root cause, contributing factors, action items, and lessons learned

## The Problem

At 14:32 UTC, users started reporting that the payment service was failing. By 14:35, the monitoring dashboard showed 100% error rate. The outage lasted 45 minutes. You have four evidence sources:

1. **Packet capture** - TCP resets, DNS NXDOMAIN responses, and BGP UPDATE messages from the core router
2. **Syslog** - Router and switch logs showing interface flaps, BGP state changes, and OSPF reconvergence
3. **Application logs** - The payment service log showing database connection timeouts and retry storms
4. **BGP updates** - Route withdrawals and re-announcements from the edge router

The challenge is that each evidence source tells a fragment of the story. The packet capture shows TCP resets but not why. The syslog shows BGP withdrawal but not the user impact. The application logs show timeouts but not the network cause. You must correlate all four sources into a single timeline, identify the causal chain, and determine the root cause.

This capstone asks you to build an evidence correlation engine in Python that ingests all four evidence sources, aligns them on a timeline, identifies co-occurring events, and produces a root-cause analysis. You must then write a production-grade postmortem document.

## The Approach

The methodology follows seven stages:

1. **Evidence ingestion** - Parse each evidence source into a structured event with a timestamp, source, layer, event type, and description. Normalize all timestamps to UTC.

2. **Timeline construction** - Merge all events from all sources into a single chronological timeline. Sort by timestamp. Tag each event with its source layer (L2, L3, L4, L7, routing).

3. **Causal chain identification** - Look for causal patterns: a BGP withdrawal at L3 precedes TCP resets at L4, which precede application timeouts at L7. Build a directed acyclic graph (DAG) of cause -> effect.

4. **Root cause isolation** - The root cause is the earliest event in the causal chain that is not itself caused by a prior event. It is the "first domino." Everything after it is a symptom or cascading effect.

5. **Contributing factor analysis** - Identify events that made the outage worse but are not the root cause: e.g., missing monitoring, no failover, aggressive retry timers causing retry storms.

6. **Impact assessment** - Quantify the outage: duration, affected users, error rate, revenue impact (if data available).

7. **Postmortem generation** - Produce a structured postmortem: Summary, Timeline, Root Cause, Contributing Factors, Impact, Action Items, Lessons Learned.

## Build It

1. Define dataclasses for EvidenceEvent, TimelineEntry, CausalLink, PostmortemSection, and IncidentReport.
2. Implement evidence ingestion: parse synthetic packet capture, syslog, application log, and BGP update sources into structured events.
3. Implement timeline construction: merge and sort all events by timestamp, tag with source layer.
4. Implement causal chain identification: detect patterns where L3 events precede L4 events precede L7 events.
5. Implement root cause isolation: find the earliest event with no preceding causal predecessor.
6. Implement contributing factor analysis: identify events that amplified the outage.
7. Implement impact assessment: compute outage duration, peak error rate, affected services.
8. Implement postmortem generation: produce a structured document with all required sections.
9. Run `code/main.py` and study the correlated timeline, causal chain, root cause, and postmortem.

## Expected Outcomes

When you run `code/main.py` you should observe:

- Four evidence sources: 120 packet capture events, 45 syslog entries, 30 application log entries, 15 BGP updates
- A merged timeline of 210 events sorted by timestamp, tagged with source layer
- Causal chain: BGP route withdrawal (L3, 14:32:05) -> route table convergence (L3, 14:32:10) -> packets routed to black hole (L3, 14:32:12) -> TCP resets (L4, 14:32:15) -> database connection timeouts (L7, 14:32:20) -> payment service errors (L7, 14:32:25)
- Root cause: BGP route withdrawal due to a misconfigured route-map that filtered the payment service's /24 prefix
- Contributing factors: no BGP route monitoring, no automatic failover, aggressive retry timer (100ms) causing retry storm
- Impact: 45-minute outage, 100% error rate, ~50,000 failed transactions
- A complete postmortem document with all sections filled

## Deliverables

- `outputs/correlated-timeline.txt` - The merged timeline of all events with layer tags and source attribution
- `outputs/causal-chain.txt` - The identified causal chain from root cause through symptoms
- `outputs/root-cause-analysis.txt` - The root cause with evidence and contributing factors
- `outputs/postmortem.md` - The complete production-grade postmortem document
- `outputs/evidence-correlation-runbook.md` - A runbook for performing multilayer incident postmortems

## Exercises

1. Add a fifth evidence source: NetFlow records. How does flow-level data change the causal chain? Can you identify the exact flows that were black-holed?
2. Model a second outage scenario: a DNS misconfiguration causes NXDOMAIN for the payment service hostname. How does the causal chain differ from the BGP scenario?
3. Implement automated alerting: if the correlation engine detects a causal chain forming, trigger an alert before the full outage develops. What is the earliest detectable signal?
4. Add a blameless postmortem mode: ensure the postmortem document uses neutral language and focuses on systemic causes, not individual blame. Rewrite the action items accordingly.
5. Model a cascading failure: the payment service outage triggers a retry storm that overloads the database, which then crashes. How does the causal chain extend? What is the difference between root cause and trigger?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Root cause | Why it broke | The earliest event in the causal chain that is not itself caused by a prior event - the first domino |
| Causal chain | The domino effect | A sequence of events where each event causes the next: root cause -> symptoms -> cascading failures |
| Contributing factor | What made it worse | An event or condition that amplified the outage but is not the root cause (e.g., missing monitoring) |
| Evidence correlation | Connecting the dots | Aligning events from multiple sources (packets, logs, routing) on a timeline to reconstruct what happened |
| Postmortem | The blameless writeup | A structured document: Summary, Timeline, Root Cause, Contributing Factors, Impact, Action Items, Lessons Learned |

## Further Reading

- Google SRE Book - "Postmortem Culture: Learning from Failure" (Chapter 15)
- "The Field Guide to Understanding 'Human Error'" by Sidney Dekker
- RFC 5424 - The Syslog Protocol
- Wireshark "Follow TCP Stream" and BGP update filter: `bgp.update.path_attributes`
- Etsy's blameless postmortem template: https://codeascraft.com/2012/05/22/blameless-postmortems/