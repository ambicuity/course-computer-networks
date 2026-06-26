# High Latency Video Call to Intermittent Wi-Fi Loss

> A user on a video call sees the other participant freeze for half a second every few seconds, audio cuts out, and the video codec drops to 240p. The first instinct is "the Wi-Fi is bad," but Wi-Fi signal strength looks fine in the OS status bar and the router admin page shows a healthy link rate. The actual fault may be Wi-Fi *or* it may be bufferbloat in the upstream router, RF interference from a neighbor's mesh network, a misconfigured 802.11r/k/v roaming threshold, a duplex mismatch on the wired uplink, or a misbehaving QoS queue on the egress ISP. This lesson walks through the diagnostic discipline for latency-sensitive real-time applications: a four-step evidence chain that separates RF-layer problems from queueing problems from application-layer problems, and uses a synthetic jitter/loss/throughput generator to model each case. The trace shows the difference between 5 ms of jitter (acceptable), 80 ms of jitter (codec stalls), and 200 ms of one-way delay (interactive conversation breaks down).

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 06 802.11 Wi-Fi, Phase 08 TCP/UDP and queuing, Phase 12 RTP basics, Lesson 01 of this phase
**Time:** ~120 minutes

## Learning Objectives

- Distinguish four failure classes for "video call quality is bad": RF-layer loss/retransmit, bufferbloat in the access queue, Wi-Fi roaming hysteresis misconfiguration, and application codec misconfiguration, each of which produces a different evidence signature in ping/jitter and iperf traces.
- Apply a four-step diagnostic chain (iperf3 UDP jitter, ping with RFC 4448 style ICMP timestamps, `tc -s qdisc` for queue depth, RF layer-2 retransmits) to identify which layer is producing the latency.
- Explain the difference between throughput-limited applications (file downloads) and latency-limited applications (VoIP, video calls) and why a connection with 200 Mbps of available bandwidth can still have a 400 ms one-way delay.
- Compute the headroom budget for a real-time interactive call: end-to-end one-way delay must be < 150 ms for natural conversation, < 250 ms for tolerable, and > 400 ms means turn-taking collapses.
- Diagnose bufferbloat by measuring the difference between idle ping RTT and loaded ping RTT — the difference is the standing queue delay, and a healthy router keeps it < 5 ms.
- Read the 802.11 station-statistics counters (`tx_retries`, `rx_dropped_misc`, beacon-loss events) and explain how a high `tx_retries` count on a single station is conclusive evidence of an RF-layer problem on that station alone.

## The Problem

A company has deployed a soft-phone and video-conferencing system to all employees. The system is working from office wired connections and from home cable/fiber links. But a subset of users — those connecting from a particular campus building with dense Wi-Fi — report consistent problems: video freezes every 3–10 seconds, audio dropouts, the codec drops from 1080p to 240p within seconds of joining a call, and the call sometimes disconnects entirely. The help-desk tickets say "Wi-Fi is bad in building C." The network team has checked the controller and sees all APs reporting "healthy." The signal strength reported by the OS is "excellent" (-52 dBm). Link rate is reported as 866 Mbps (802.11ac, 2×2 MIMO).

The four most likely candidates, all of which the symptoms are consistent with, are:

- **Bufferbloat in the home router or AP uplink**: The AP has a 1 Gbps link to the upstream switch, but the WAN link to the internet is 50 Mbps. The AP's egress queue is sized at 1000 packets; when the link is fully loaded (someone else on the LAN downloads a large file), the queue fills and standing delay can reach 800 ms. The Wi-Fi itself is fine; the latency is being injected by a queue in the path.
- **RF interference / hidden-node problem**: The campus has 47 APs from three vendors, and the 5 GHz spectrum is congested. A specific AP in building C is being overwhelmed by co-channel interference from two neighboring APs on the same channel, and clients see constant retransmits at the 802.11 layer.
- **Roaming hysteresis misconfiguration**: 802.11r/k/v fast-roaming is enabled with a signal threshold that is too aggressive, causing clients to "ping-pong" between APs. Each roam takes 100–500 ms, and during the roam the client sees 100% loss for that duration.
- **Application codec misconfiguration**: The soft-phone is configured with a 200 ms jitter buffer (the default in some legacy systems), and the codec's PLC (Packet Loss Concealment) is set to "low" instead of "high." The network is healthy, but the jitter buffer cannot absorb the natural variation in packet arrival.

The first responder's job is to determine which of these is actually happening. The diagnostic chain in this lesson exists to disambiguate them.

## The Concept

### The Four-Layer Latency Stack for Real-Time Apps

Real-time interactive applications (VoIP, video calls, remote desktop) are sensitive to latency, jitter, and loss in a way that bulk-data applications are not. The latency budget for a typical transcontinental VoIP call breaks down as:

| Layer | Typical contribution | Failure mode |
|-------|----------------------|--------------|
| Application codec | 20–80 ms (algorithmic + jitter buffer) | Codec too aggressive, jitter buffer too small or too large |
| 802.11 Wi-Fi | 1–30 ms | RF interference, retries, roaming |
| Wired LAN | < 1 ms | Queueing, duplex mismatch |
| ISP / Internet | 20–80 ms (transcontinental) | Bufferbloat, congestion |
| Codec + de-jitter buffer at far end | 40–120 ms | Inconsistent |

A healthy transcontinental call has an end-to-end one-way delay of 100–150 ms. Beyond 250 ms, the participants start talking over each other because the round-trip time exceeds the human "turn-taking" threshold (about 500 ms). Beyond 400 ms, the conversation becomes push-to-talk, and at 800 ms it collapses entirely.

The four diagnostic commands in this lesson map to these four layers:

| Command | Measures | Layer | Failure signature |
|---------|----------|-------|-------------------|
| `iperf3 -u -b 5M -t 30 -J` | UDP throughput, jitter, loss | App + Wi-Fi | High loss + low jitter = RF; high jitter + low loss = queue |
| `ping -c 100 -i 0.1 <gateway>` | Idle and loaded RTT | Queue | Loaded RTT - idle RTT > 50 ms = bufferbloat |
| `tc -s qdisc show dev wlan0` | Queue depth, drops | Queue | `backlog` non-zero and `drops` rising |
| Station stats (`/proc/net/...` or vendor MIB) | L2 retransmits, beacon loss | RF | `tx_retries` > 10% of `tx_packets` = RF problem |

### Bufferbloat: The Hidden Latency Killer

Bufferbloat is the phenomenon of large packet queues in home routers, APs, and ISP equipment producing hundreds of milliseconds of standing delay under load. The mechanism:

1. A 1 Gbps link exists between the AP and the upstream switch
2. A 50 Mbps link exists between the AP and the WAN
3. The AP's egress queue to the WAN is sized for the fast link (1000+ packets)
4. When the WAN link is fully loaded, the queue fills with up to 1000 packets
5. Each packet in the queue adds its serialization time to the standing delay
6. With 1500-byte packets and a 50 Mbps link, each packet's serialization time is 240 µs — so 1000 packets = 240 ms of standing delay
7. A VoIP packet arriving at the back of the queue waits 240 ms before being sent

The signature is unmistakable: the idle RTT (when no one else is using the link) is 30 ms, and the loaded RTT (when someone downloads a large file) is 270 ms. The difference of 240 ms is the bufferbloat. The fix is to enable an Active Queue Management (AQM) algorithm like CAKE (Common Applications Kept Enhanced) or fq_codel on the bottleneck link's egress queue. CAKE is specifically designed for home routers and intelligently manages per-flow queues to keep standing delay below 5 ms.

### 802.11 RF Interference and Retry Behavior

The 802.11 MAC uses CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance). When a station transmits a frame, it expects an ACK within a SIFS (Short Inter-Frame Space) of 16 µs. If no ACK arrives, the station retransmits with a doubled contention window. The retry counters exposed by the driver are the smoking gun:

- **`tx_retries`**: Number of frames that required one or more retransmissions
- **`tx_failed`**: Number of frames that exhausted all retries (default 7 for data frames)
- **`retry_count_per_frame`**: Average number of retries per successful frame

A healthy 802.11 link has `tx_retries / tx_packets < 5%`. A link with `tx_retries / tx_packets > 20%` is in serious trouble. A link with `tx_retries / tx_packets > 50%` is essentially unusable for real-time applications.

The station-statistics counters are available in:
- Linux: `iw dev wlan0 station dump` (limited), `/sys/kernel/debug/ieee80211/<phy>/netdev:<iface>/stations/<MAC>` (driver-specific)
- macOS: `wdutil info`, Wireless Diagnostics
- Windows: `netsh wlan show interfaces`
- Vendor-specific: Cisco AP `show client ap <mac>`, Aruba `show station-table`

A `tx_retries` count that is high on a single station but low on all other stations is conclusive evidence of an RF-layer problem on that station alone — the surrounding RF environment is fine, but the link from the AP to this specific station is bad. Possible causes: the station is too far from the AP, the station has a damaged antenna, there is a physical obstruction (metal filing cabinet) between the station and the AP, or the station's 5 GHz radio is failing.

### Wi-Fi Roaming and Fast Transition (802.11r/k/v)

Modern enterprise Wi-Fi supports 802.11r (Fast BSS Transition, FT), 802.11k (Radio Resource Management, RRM), and 802.11v (BSS Transition Management). These are designed to make roaming seamless:

- **802.11k**: Provides the client with a "neighbor report" listing nearby APs, their channels, and signal strengths. The client uses this to make faster roaming decisions.
- **802.11v**: Allows the AP to suggest that a client should roam to a different BSS (Basic Service Set, i.e., a different AP) based on load or signal.
- **802.11r**: Reduces the 802.1X re-authentication time from ~500 ms to < 50 ms by pre-negotiating the key material.

The failure mode: if 802.11r is enabled but the APs are not all configured with the same mobility domain, the client will attempt an FT roam, fail to find a matching mobility domain, fall back to a full 802.1X re-auth, and experience 500 ms of loss. This is a configuration problem, not a coverage problem. The signature is: latency is fine while the user is stationary, and the user sees 500 ms blips every 30–120 seconds as the client roams.

The diagnostic: enable roaming logs on the client (`log show --predicate 'subsystem == "com.apple.wifi"'` on macOS, or `wpa_supplicant -ddd` on Linux) and look for FT roam attempts and their outcomes. On the AP side, enable RRM logging and look for "neighbor report" responses.

### Codec, Jitter Buffer, and PLC

The application-layer end of the latency budget is often overlooked. A typical VoIP stack has:

- **Codec algorithmic delay**: G.711 has 0 ms (sample-based), G.722 has 4 ms, Opus has 6.5–22.5 ms, AAC-LD has 20 ms
- **Frame size**: 20 ms is standard for VoIP, 10 ms is low-latency
- **Jitter buffer (de-jitter buffer)**: 60–200 ms typical, designed to absorb network jitter
- **PLC (Packet Loss Concealment)**: Synthesizes a replacement frame when one is lost; takes 0–20 ms

The total codec-and-buffer delay is typically 80–200 ms. A 200 ms jitter buffer is too large for an interactive call and will make the call feel sluggish. A 40 ms jitter buffer is too small and will produce frequent PLC artifacts.

The signature of a codec misconfiguration: the network is healthy (low loss, low jitter, low RTT), but the user-perceived quality is still bad, and `mos` (Mean Opinion Score) estimates from the softphone are low. The fix: reduce the jitter buffer to 60–80 ms, increase PLC aggressiveness to "high," and verify the codec's PLC settings are not "disabled."

### The Four-Step Diagnostic Chain

| Step | Command | Healthy output | Problem output | Points to |
|------|---------|----------------|----------------|-----------|
| 1 | `iperf3 -u -b 5M -t 30 -c <gw> -J` | jitter < 5 ms, loss < 0.1% | jitter > 30 ms, loss > 2% | Wi-Fi or queue |
| 2 | `ping -c 100 -i 0.1 <gw>` (idle) and again with `iperf3 -u -b 50M` running in parallel | idle RTT < 50 ms, loaded RTT within 10 ms of idle | loaded RTT > 200 ms | Bufferbloat |
| 3 | `iw dev wlan0 station dump` or vendor MIB | `tx_retries/tx_packets < 5%` | `tx_retries/tx_packets > 20%` | RF interference or distance |
| 4 | Application logs: jitter buffer, PLC events, codec bitrate adaptation | Stable at 64 kbps, no PLC events | PLC events spiking, bitrate drops | Codec or application |

The order matters: each step's evidence is more specific than the previous. A high `tx_retries` count is conclusive evidence of an RF problem and ends the investigation. A high loaded RTT with low RF retries is conclusive evidence of bufferbloat. A healthy network with PLC events spiking is conclusive evidence of an application/codec problem.

## Build It

The `code/main.py` in this lesson simulates the four failure classes and walks the four-step diagnostic chain for each. It generates synthetic per-packet latency, loss, and retransmit data for a 30-second window, then computes the chain's outputs. The simulator is stdlib-only and deterministic.

1. **Read** `code/main.py`. Notice the `FailureMode` enum, the `PacketTrace` class that generates per-packet data using a deterministic seeded RNG, and the four diagnostic functions `measure_throughput_jitter`, `measure_rtt_idle_vs_loaded`, `measure_rf_retransmits`, and `measure_codec_events`.
2. **Run** `python3 code/main.py --mode bufferbloat` (or `--mode rf_interference`, `--mode roaming`, `--mode codec`). You will see the synthetic packet trace summary, then the four-step diagnostic chain, then a verdict.
3. **Compare** the four modes side by side: `python3 code/main.py --mode all`. The output will show that the first decisive evidence differs in each case.
4. **Modify** the `FailureMode.BUFFERBLOAT` parameters to use 1500-byte packets and a 10 Mbps link — observe how the standing delay changes. The formula is `standing_delay = queue_depth × (packet_size_bits / link_bps)`.

The simulator's lesson: the *method* is constant across all four failure classes. Only the *evidence* and the *culprit* change.

## Use It

| Symptom | Diagnostic Command | Expected Output | Culprit |
|---------|-------------------|-----------------|---------|
| Video freezes every few seconds | `iperf3 -u -b 5M -t 30 -c <gw> -J` | jitter > 30 ms, loss > 2% | Wi-Fi RF or queue |
| Video freezes during heavy download | `ping <gw>` (during download) | loaded RTT > 200 ms | Bufferbloat |
| Video freezes only while moving | `iw station dump` (check roam count) | `roam_count` > 0, FT roams logged | Roaming misconfig |
| Video freezes despite clean network | `mos` score from softphone | MOS < 3.5 | Codec or jitter buffer |
| All other stations healthy | `iw station dump` for all stations | One station has high `tx_retries`, others normal | RF problem on one client |
| AQM status | `tc -s qdisc show dev eth0` | `backlog 0b 0p`, `drops 0` | Queue is fine |
| AQM status (broken) | `tc -s qdisc show dev eth0` | `backlog 50Kb 30p`, `drops 1234` | Queue is bloated |
| Wired clients fine, Wi-Fi clients bad | `iperf3 -s` on AP | Wired clients get 800 Mbps, Wi-Fi clients get 50 Mbps | Wi-Fi bottleneck |
| 5 GHz clients fine, 2.4 GHz clients bad | `iw station dump` on 2.4 GHz | High `tx_retries` on 2.4 GHz | 2.4 GHz interference |
| Roaming at threshold -75 dBm | `wpa_supplicant -ddd` | FT roam attempt logged | Roaming threshold correct |

## Ship It

The `outputs/prompt-high-latency-video-call-to-intermittent-wi-fi-loss.md` file is your deliverable. Author a one-page runbook for "video call quality is bad on Wi-Fi" that contains:

1. The four-step diagnostic chain with one-line decision rules.
2. A reference table of healthy vs. problematic values for the four key metrics (jitter, loaded RTT, retry ratio, MOS score).
3. A list of three common false-positive pitfalls: (a) signal strength in dBm is not the same as link quality — a -52 dBm signal with 30% retries is worse than a -65 dBm signal with 1% retries, (b) the OS status bar reports the highest link rate negotiated, not the actual throughput, (c) the AP's "healthy" status means it can talk to the controller, not that its clients are getting good service.
4. An "intervention menu" with the specific knobs to tune for each failure class (e.g., for bufferbloat: enable CAKE; for RF: change channel or AP density; for roaming: tune 802.11r/k/v thresholds).

## Exercises

1. **Latency budget**: For a transcontinental VoIP call, codec = Opus 20 ms frame, jitter buffer = 60 ms, 802.11 = 5 ms, wired LAN = 2 ms, ISP RTT = 50 ms. What is the end-to-end one-way delay? Is this within the "natural conversation" budget?
2. **Bufferbloat math**: A 50 Mbps link with 1500-byte packets and a queue depth of 200 packets. What is the standing delay? If the link is upgraded to 200 Mbps with the same packet size, what is the new standing delay? (Hint: `delay = queue_depth × packet_size / link_rate`.)
3. **Retry ratio**: A station has `tx_packets = 100,000` and `tx_retries = 8,500`. What is the retry ratio? Is this acceptable? At what ratio does 802.11 become unusable for real-time applications?
4. **Roaming blip**: A user sees 500 ms blips every 30 seconds. The network team says signal is "excellent." What is the most likely cause? What command confirms it?
5. **Codec vs. network**: MOS score is 3.2, network jitter is 4 ms, loss is 0.1%, loaded RTT is 45 ms. Is the fault network or application? What would you do first?
6. **Compare with lesson 01**: Lesson 01's physical-to-application chain looks for *complete* failure (no service at all). This lesson's chain looks for *quality* degradation (service works but is poor). How does the diagnostic chain change between these two cases? (Hint: lesson 01 uses a single decisive piece of evidence; this lesson often needs all four steps to fully characterize the problem.)

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| Bufferbloat | A cute name for a serious problem | Excessive buffering in network equipment that produces high standing delay under load |
| AQM | Some kind of queue | Active Queue Management — algorithms like RED, CoDel, fq_codel, CAKE that keep queues short |
| CAKE | The dessert | Common Applications Kept Enhanced — an AQM designed for home routers that achieves < 5 ms standing delay |
| Jitter | A musical instrument | Variation in packet arrival time, measured in milliseconds; the standard deviation or max-min of inter-arrival times |
| 802.11r | A standard revision | Fast BSS Transition — reduces roam-time 802.1X re-authentication from ~500 ms to < 50 ms |
| 802.11k | A standard revision | Radio Resource Management — neighbor reports that help clients find better APs |
| 802.11v | A standard revision | BSS Transition Management — AP-initiated roam suggestions |
| Jitter buffer | A memory allocation | A de-jitter buffer that smooths out network jitter at the cost of added delay |
| PLC | Programmable Logic Controller | Packet Loss Concealment — a codec feature that synthesizes a replacement frame when one is lost |
| MOS | A type of score | Mean Opinion Score — a 1–5 quality rating for voice calls, predicted by codec and network conditions |

## Further Reading

- **RFC 3550** — *RTP: A Transport Protocol for Real-Time Applications*. The protocol VoIP and video-conferencing use, including the RTCP reports that estimate jitter and loss.
- **RFC 8285** — *A Per-Segment Header Compression Extension for RTP*. The mechanism for compressing RTP headers in low-bandwidth links.
- **Bufferbloat Project** — https://www.bufferbloat.net/. The community resources for understanding, diagnosing, and fixing bufferbloat. Includes the CAKE algorithm description.
- **IEEE 802.11-2020** — the consolidated 802.11 standard, including the station statistics counters and the 802.11r/k/v amendments.
- **iperf3 documentation** — https://software.es.net/iperf/. The `-J` flag produces JSON output with the `jitter_ms` and `lost_percent` fields used in the diagnostic chain.
- **Apple's Wi-Fi roaming logs** — `log show --predicate 'subsystem == "com.apple.wifi" AND eventMessage CONTAINS "roam"'`. Useful for client-side roam analysis on macOS.
- **phases/06-ethernet-wireless-lans-and-switching** — 802.11 PHY and MAC fundamentals, including the CSMA/CA retry behavior.
- **phases/08-tcp-and-udp** — UDP's lack of retransmission and the implications for real-time applications.
- **phases/17-integrated-troubleshooting-labs/01-physical-to-application-outage-trace** — the parent lesson's bottom-up methodology that this lesson specializes for latency-sensitive apps.
- **phases/17-integrated-troubleshooting-labs/04-mtu-black-hole** — the MTU-related latency failures (large-packet retransmits, ICMP black-holed DF).
