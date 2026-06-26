# RTP and RTCP Packet Trace Lab

> RTP carries the media. RTCP carries the quality reports. Together they let the receiver tell the sender exactly how the stream is performing.

**Type:** Lab
**Languages:** Python, packet traces, Wireshark
**Prerequisites:** Phase 13 lessons 01-13 (Real-time Conferencing, RTSP)
**Time:** ~75 minutes

## Learning Objectives

- Decode the RTP fixed header: version, payload type, sequence number, timestamp, SSRC
- Identify RTCP packet types: SR (Sender Report), RR (Receiver Report), SDES, BYE
- Compute packet loss, jitter, and round-trip time from RTCP reports
- Build a trace annotator that summarizes an RTP/RTCP session
- Connect RTCP statistics to observable quality metrics

## The Problem

When a real-time media stream degrades (choppy audio, frozen video), the engineer needs to know: is it packet loss? jitter? out of order? RTP carries the media but provides no feedback channel. RTCP (RTP Control Protocol) solves this by periodically sending quality reports back to the sender. Reading these reports tells you exactly what the receiver experienced.

## The Concept

### RTP header (12 bytes fixed)

```text
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CSRC  |M|     PT      |       sequence number         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           timestamp                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           synchronization source (SSRC) identifier             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **V**: version (2)
- **P**: padding
- **X**: extension header present
- **CSRC count**: number of contributing source identifiers
- **M**: marker bit (frame boundary)
- **PT**: payload type (e.g., 0 = PCMU, 8 = PCMA, 96+ = dynamic)
- **Sequence number**: increments by 1 per packet, detects loss and reordering
- **Timestamp**: sampling instant, clock rate depends on codec (8000 for voice)
- **SSRC**: identifies the synchronization source (the stream)

### RTCP packet types

| Type | Name | Purpose |
|------|------|---------|
| 200 | SR (Sender Report) | Sender stats: packets sent, bytes sent, NTP timestamp |
| 201 | RR (Receiver Report) | Receiver stats: fraction lost, cumulative lost, jitter, LSR, DLSR |
| 202 | SDES | Source description: CNAME, name, email, phone, loc, tool, note |
| 203 | BYE | End of session, optional reason string |
| 204 | APP | Application-specific extensions |

### Key RTCP receiver report fields

- **Fraction lost**: percentage of packets lost since last report (8 bits, fixed-point)
- **Cumulative packets lost**: total lost since start (24 bits)
- **Highest sequence number received**: with wrap-around cycle count
- **Interarrival jitter**: smoothed estimate of jitter in timestamp units
- **LSR (Last SR)**: NTP timestamp of last sender report received
- **DLSR (Delay since last SR)**: delay between receiving SR and sending this RR

### Round-trip time calculation

```text
RTT = NTP_now - LSR - DLSR
```

The sender includes its NTP timestamp in SR. The receiver echoes it as LSR and adds DLSR (time elapsed since receiving that SR). When the sender receives the RR, it computes RTT.

## Build It

The script below simulates an RTP/RTCP session and generates a trace you can annotate. It demonstrates:

1. RTP packet generation with realistic header fields
2. Network simulation with loss, jitter, and reordering
3. RTCP SR/RR report generation and parsing
4. Jitter calculation from interarrival time differences
5. RTT estimation from LSR/DLSR exchange
6. A trace summary annotator

```python
# Core idea (see code/main.py)
for packet in rtp_stream:
    if random_loss():
        receiver.lost += 1
    else:
        jitter = compute_jitter(arrival_time, packet.timestamp)
        receiver.receive(packet)
    if time_for_rtcp():
        rr = receiver.build_rr()
        sender.process_rr(rr)
```

## Use It

```bash
python3 code/main.py
```

Expected output: a packet trace showing each RTP packet with its header fields, RTCP reports with computed statistics, and a session summary including loss rate, average jitter, and estimated RTT.

## Ship It

- Use the trace annotator as a template for analyzing real Wireshark captures. Filter by `rtp` or `rtcp` and match the output fields.
- Extend the simulator to support multiple SSRCs (multi-party call) and show per-stream reports.
- Export the statistics as JSON for integration with a monitoring dashboard.

## Exercises

1. Increase the loss rate from 2% to 10% and observe how the fraction lost and cumulative lost fields change.
2. Add a constant 50ms delay to all packets and show that jitter stays low (jitter measures variation, not absolute delay).
3. Vary the delay randomly and show how the jitter estimate grows.
4. Implement SDES and BYE packets and show the full session lifecycle.
5. Compute the MOS score from the RTCP loss statistics and compare with the ITU-T G.107 E-model.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| RTP | "Media packets" | Real-time Transport Protocol, carries timestamped media over UDP with sequence numbers |
| RTCP | "Control packets" | RTP Control Protocol, sends quality reports (loss, jitter, RTT) between sender and receiver |
| SSRC | "Stream ID" | Synchronization Source identifier, uniquely identifies one media stream in an RTP session |
| SR | "Sender report" | Sender Report RTCP packet with sender stats and NTP timestamp for RTT calculation |
| RR | "Receiver report" | Receiver Report RTCP packet with loss, jitter, and delay since last SR |
| LSR | "Last sender time" | The NTP timestamp from the last SR, echoed back in RR for RTT computation |
| DLSR | "Delay since SR" | Time between receiving an SR and sending the matching RR, used in RTT calculation |
| Jitter | "Network wobble" | Smoothed variation in packet interarrival time, measured in RTP timestamp units |

## Further Reading

- [RFC 3550 - RTP](https://www.rfc-editor.org/rfc/rfc3550) - the definitive standard for RTP and RTCP
- [Wireshark RTP analysis](https://wiki.wireshark.org/RTP) - capture and analysis guide
- [RFC 3551 - RTP Profile](https://www.rfc-editor.org/rfc/rfc3551) - audio/video profile with payload type assignments
