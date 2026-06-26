# Debug a Realistic Outage / Build a Minimal Reliable Protocol

> Trace TCP RSTs through a live e-commerce outage, then implement stop-and-wait and sliding-window ARQ from scratch in Python to understand why every mechanism exists.

**Type:** Capstone
**Languages:** Python (stdlib only), Wireshark, shell
**Prerequisites:** Phase 6 TCP deep-dive, Phase 10 transport layer, Phase 17 troubleshooting methodology
**Time:** ~180 minutes

---

## Learning Objectives

After completing both tracks you will be able to:

**Debugging track**
1. Use Wireshark display filters (`tcp.flags.reset==1`, `tcp.analysis.retransmission`) to isolate RST storms and retransmission spikes in a packet capture.
2. Distinguish between a client-originated RST, a load-balancer-originated RST, and a server-originated RST by reading IP source addresses and TCP sequence numbers in the trace.
3. Map a TCP RST back to a specific misconfiguration — idle-timeout mismatch, half-open connection, or abrupt process death — by correlating packet timing with application logs.

**Protocol-building track**
4. Implement stop-and-wait ARQ in Python, including sequence numbering, ACK handling, retransmission on timeout, and deliberate loss injection for testing.
5. Extend the implementation to a fixed-size sliding window (Go-Back-N) and measure the throughput difference under simulated 5% loss.
6. Explain why sequence numbers must be larger than the window size and why the TIME_WAIT state exists, with reference to your own running code.

---

## The Problem

### Part 1 — The Outage

It is 14:23 on a Tuesday. The on-call engineer at a mid-size e-commerce company receives a PagerDuty alert: checkout conversion has dropped 34% in the last five minutes. The frontend is healthy. The CDN shows green. Application logs on the order service show a flood of `Connection reset by peer` errors, each one paired with a half-completed order write. Customer support is fielding refund requests.

The network team pulls a packet capture from the load balancer and opens it in Wireshark. Applying the filter `tcp.flags.reset==1` immediately reveals hundreds of RST packets per minute, all sourced from the load balancer's internal IP (`10.0.1.1`) and directed at the order service backends (`10.0.2.11–10.0.2.14`). The sequence numbers in the RSTs match the sequence numbers of in-flight POST requests, not fresh SYN packets. That rules out a SYN flood. A second filter, `tcp.analysis.retransmission`, shows the backends are each retransmitting the same data segment three to five times before the RST arrives — a sign that the load balancer already considers the connection dead while the backend is still trying to send.

The smoking gun emerges when the team compares two timestamps: the load balancer's idle-connection timeout (60 seconds, set in the HAProxy config) against the connection pool keep-alive interval in the order service (90 seconds). Any connection that sits idle for more than 60 seconds gets silently torn down by the load balancer. The backend's connection pool does not know this happened. When the next request arrives and the pool hands out that stale descriptor, the backend writes data into a socket the load balancer has already discarded. The load balancer responds with a RST. The backend surfaces this as `Connection reset by peer`. The order fails.

The fix is a one-line config change — reduce the pool keep-alive to 50 seconds — but understanding *why* it works requires understanding what a RST actually means at the TCP layer, what sequence numbers prove about the packet's origin, and why a silent half-open connection is indistinguishable from a live one until data is transmitted.

### Part 2 — Building to Understand

That outage is a symptom of a deeper gap: TCP's reliability mechanisms are usually invisible until they break. Textbooks describe retransmission and ACKs in prose, but the timing relationships — why an ACK with the wrong sequence number causes a full retransmit, why a too-short retransmission timer saturates the network, why a window size of one is safe but slow — only become intuitive when you have written the logic yourself and watched it fail.

Part 2 of this capstone builds a minimal reliable protocol over UDP using Python's `socket` module (no third-party libraries). You will implement stop-and-wait ARQ first because it is the simplest correct design: send one segment, wait for its ACK, retransmit on timeout. Then you will extend to a fixed sliding window, observe the throughput improvement, and understand precisely which invariant the larger sequence-number space protects. By the end, every mechanism in the outage trace above will map to a line of code you wrote.

---

## The Concept

### Stop-and-Wait ARQ

Stop-and-wait Automatic Repeat reQuest is the minimal reliable-delivery protocol. The sender transmits one segment, starts a retransmission timer, and blocks until it receives an ACK for that segment or the timer fires. On timeout, it retransmits the same segment. The receiver sends an ACK after every correctly received segment. A single-bit sequence number (0 or 1, the "alternating bit") is sufficient to distinguish a new segment from a retransmit.

Throughput is bounded by the bandwidth-delay product divided by segment size. On a 100ms RTT link with a 1 KB segment, utilization is at most 1 KB / (RTT × bandwidth). On a 10 Mbps link that works out to roughly 0.08% utilization — fine for a serial printer, catastrophic for a data center.

### Sliding Window and Go-Back-N

A sliding window allows the sender to have up to W unacknowledged segments in flight simultaneously. The sender maintains a send window `[base, base+W)`. When `ACK(n)` arrives, the window slides forward so that `base = n+1`. The receiver in Go-Back-N (GBN) maintains only a single expected sequence number; any out-of-order segment is discarded and a cumulative ACK for the last in-order segment is sent. In Selective Repeat (SR), the receiver buffers out-of-order segments and ACKs them individually, reducing unnecessary retransmits at the cost of receiver-side buffer complexity.

Sequence numbers must span at least `2W` values in GBN (and `2W` values in SR as well, though the reasoning differs) to prevent the receiver from confusing an old retransmit with a new segment after a window wrap. This is not a theoretical concern — it is why TCP's initial sequence number is chosen randomly, and why sequence-number exhaustion on very fast, very long-distance links motivated the TCP timestamp option.

### TCP RSTs and the Three-Way Handshake

A TCP RST is an abrupt connection teardown. Unlike a FIN (which begins an orderly four-packet close), a RST immediately invalidates the connection on both sides. A RST is legitimate when it carries a sequence number within the receiver's current window — this is what the load balancer exploits: it knows the sequence number because it proxied the connection. A RST with a sequence number outside the window is silently dropped, which is why RST-injection attacks must first guess or sniff the current sequence number.

```
                  CLIENT              LOAD BALANCER         BACKEND
                    |                      |                    |
    SYN ----------->|  SYN --------------->|  SYN ------------> |
                    |  SYN-ACK <---------- |  <----------- SYN-ACK
    SYN-ACK <-------|  ACK --------------->|  ACK ------------> |
    ACK ----------->|                      |  [connection open] |
                    |                      |                    |
     ... (idle > 60s, LB removes state) ...|                    |
                    |                      |                    |
    POST  --------> |  POST -------------> |  POST -----------> |
                    |                      |  DATA <----------- |  (backend writes)
                    |                      |  RST ------------> |  (LB: unknown conn)
                    |  RST  <------------- |
    RST  <--------- |
                    |   "Connection reset by peer"
```

### Retransmission Timer

The retransmission timeout (RTO) in TCP is computed from a running estimate of round-trip time (RTT) using Jacobson's algorithm: `SRTT = (1-α)·SRTT + α·RTT_sample` and `RTTVAR = (1-β)·RTTVAR + β·|SRTT - RTT_sample|`, with `RTO = SRTT + 4·RTTVAR`. The key insight is that the RTO must be larger than the true RTT, but not so large that a single lost packet stalls the connection for seconds. In your implementation you will use a fixed timeout first, then optionally add exponential backoff (doubling on each retransmit), which mirrors TCP's behavior under sustained congestion.

---

## Build It

### Track A — Debug the Outage Trace

**Step 1: Reproduce the symptom in a controlled environment.**

You do not need real infrastructure. The `code/` directory contains `simulate_outage.py`, which opens two raw UDP sockets on loopback and simulates the RST-injection pattern by sending a valid data segment followed by an out-of-window RST, then a within-window RST. Run it and capture on `lo` (macOS: `lo0`):

```bash
sudo python3 code/simulate_outage.py &
sudo tcpdump -i lo -w /tmp/outage.pcap port 9000
```

Open `/tmp/outage.pcap` in Wireshark.

**Step 2: Isolate RSTs with a display filter.**

In the Wireshark display filter bar, enter:

```
tcp.flags.reset == 1
```

You should see exactly the RST packets. Note the source IP, the sequence number in the RST (`tcp.seq`), and compare it to the last ACK number the receiver sent (`tcp.ack` in the preceding packet). If `tcp.seq` falls within the receiver's window (`last_ack <= tcp.seq < last_ack + window_size`), the RST is legitimate and will be accepted.

**Step 3: Identify retransmissions.**

Remove the RST filter and apply:

```
tcp.analysis.retransmission or tcp.analysis.fast_retransmission
```

Wireshark's TCP analysis engine marks retransmissions automatically. Note the delta time between original transmission and first retransmit — this is the RTO in effect at that moment. In a real trace from the outage scenario described, you would expect to see three to five retransmits at roughly 200ms, 400ms, 800ms intervals (exponential backoff) before the RST terminates the connection.

**Step 4: Pinpoint the RST source.**

Use the combined filter:

```
tcp.flags.reset == 1 and ip.src == 10.0.1.1
```

The IP source `10.0.1.1` is the load balancer. Compare with:

```
tcp.flags.reset == 1 and ip.src == 10.0.2.11
```

If both filters return packets, the load balancer and backend are both sending RSTs — a sign the state is fully desynchronized. In the simulation, only the load balancer (simulated by one socket) sends RSTs; the backend (the other socket) is the confused party sending retransmits.

**Step 5: Document root cause.**

In `outputs/trace-annotation.md`, record:
- The sequence number range of the legitimate connection before idle timeout
- The timestamp delta between last data packet and first RST
- Whether the RST falls within the receiver's advertised window
- The configuration mismatch (idle timeout vs. keep-alive interval) you infer from packet timing

---

### Track B — Build the Protocol

**Step 1: Stop-and-wait sender and receiver (single-bit sequence number).**

Create `code/arq.py`. The core sender loop:

```python
import socket, struct, time, random

TIMEOUT = 0.5   # seconds
LOSS_RATE = 0.0  # inject loss for testing

def make_segment(seq: int, data: bytes) -> bytes:
    # 1-byte header: sequence number (0 or 1)
    return struct.pack("!B", seq & 0x1) + data

def parse_segment(raw: bytes):
    seq = struct.unpack("!B", raw[:1])[0]
    return seq, raw[1:]

def send_reliable(sock, dest, data: bytes):
    seq = 0
    sock.settimeout(TIMEOUT)
    while True:
        seg = make_segment(seq, data)
        if random.random() >= LOSS_RATE:
            sock.sendto(seg, dest)
        try:
            ack_raw, _ = sock.recvfrom(2)
            ack_seq = struct.unpack("!B", ack_raw)[0]
            if ack_seq == seq:
                return   # ACK for current segment received
        except socket.timeout:
            pass  # retransmit
```

The receiver mirrors this:

```python
def recv_reliable(sock) -> bytes:
    expected = 0
    while True:
        raw, addr = sock.recvfrom(65535)
        seq, data = parse_segment(raw)
        ack = struct.pack("!B", seq)
        sock.sendto(ack, addr)
        if seq == expected:
            expected ^= 1
            return data
        # duplicate: re-ACK but do not deliver
```

Run sender and receiver in two terminals. Set `LOSS_RATE = 0.2` and observe retransmits in the terminal output (add a `print` on each attempt).

**Step 2: Measure stop-and-wait throughput.**

Send 100 segments of 1 KB each over loopback and time the total transfer:

```python
start = time.monotonic()
for i in range(100):
    send_reliable(sock, dest, b"x" * 1024)
elapsed = time.monotonic() - start
print(f"Stop-and-wait: {100 * 1024 / elapsed / 1e6:.3f} MB/s")
```

Record the result. With `LOSS_RATE = 0.0` on loopback you should see several hundred KB/s — far below the loopback bandwidth, because every segment waits for an ACK before the next is sent.

**Step 3: Extend to Go-Back-N sliding window.**

The sender now keeps a window of W unACKed segments in flight. Use a deque as the window buffer and a background thread (or `select`) to receive ACKs while sending:

```python
from collections import deque
import threading

WINDOW = 4

def send_window(sock, dest, segments: list[bytes]):
    base = 0
    next_seq = 0
    unacked = {}          # seq -> (segment, send_time)
    lock = threading.Lock()

    def receiver_thread():
        nonlocal base
        sock.settimeout(0.1)
        while base < len(segments):
            try:
                raw, _ = sock.recvfrom(2)
                ack = struct.unpack("!B", raw)[0]
                with lock:
                    if ack == base % 256:
                        base += 1
                        unacked.pop(base - 1, None)
            except socket.timeout:
                pass

    t = threading.Thread(target=receiver_thread, daemon=True)
    t.start()

    while base < len(segments):
        with lock:
            while next_seq < base + WINDOW and next_seq < len(segments):
                seg = struct.pack("!B", next_seq % 256) + segments[next_seq]
                if random.random() >= LOSS_RATE:
                    sock.sendto(seg, dest)
                unacked[next_seq] = (seg, time.monotonic())
                next_seq += 1
            # retransmit timed-out segments (Go-Back-N: retransmit from base)
            now = time.monotonic()
            if base in unacked and now - unacked[base][1] > TIMEOUT:
                for i in range(base, next_seq):
                    if i in unacked:
                        sock.sendto(unacked[i][0], dest)
                        unacked[i] = (unacked[i][0], now)
        time.sleep(0.001)
    t.join()
```

**Step 4: Measure sliding-window throughput.**

Repeat the 100-segment benchmark with `WINDOW = 4` and `WINDOW = 16`. Record all three numbers (stop-and-wait, W=4, W=16) in a comparison table.

**Step 5: Inject loss and observe Go-Back-N behavior.**

Set `LOSS_RATE = 0.05`. Add a print statement whenever the retransmit branch fires, noting which sequence numbers are retransmitted. You should observe that when segment `N` is lost, *all* segments from `N` through `next_seq - 1` are retransmitted — the defining characteristic of Go-Back-N that distinguishes it from Selective Repeat.

---

## Use It

| Task | Tool / Command | What correct output looks like |
|---|---|---|
| Find all RSTs in a capture | Wireshark: `tcp.flags.reset == 1` | A filtered list showing RST packets with source IPs, sequence numbers, and delta times |
| Confirm RST falls within receiver window | Compare `tcp.seq` (RST) against `tcp.ack` and `tcp.window_size` in preceding ACK | `tcp.seq >= last_ack AND tcp.seq < last_ack + window` evaluates true |
| Spot retransmissions caused by idle-timeout RST | `tcp.analysis.retransmission` filter, sort by time | Multiple retransmit entries for same original sequence number, growing inter-arrival gaps (backoff) |
| Verify stop-and-wait correctness under loss | Run `arq.py` sender with `LOSS_RATE=0.3`, receiver prints delivered segments | All 100 segments delivered in order despite 30% loss; delivery count equals sent count |
| Confirm Go-Back-N retransmits from base | Set `LOSS_RATE=0.1`, observe retransmit prints | Print shows retransmit starting at `base` sequence number each time, not only the lost segment |
| Compare throughput stop-and-wait vs. W=16 | Time both in `benchmark.py` | W=16 throughput is 10-15× higher under 0% loss; gap narrows as loss increases |

---

## Ship It

Commit the following to `outputs/`:

**1. Annotated trace (`outputs/trace-annotation.md`)**
A markdown table listing each relevant packet in the simulated outage capture with columns: packet number, time delta, src, dst, TCP flags, sequence number, ACK number, and a one-sentence interpretation. The final row should state the root cause in one sentence.

**2. Protocol implementation (`code/arq.py`)**
The complete Python file including stop-and-wait sender/receiver and Go-Back-N sender, with a `__main__` block that runs the benchmark automatically and prints results.

**3. Comparison chart (`outputs/comparison.md`)**
A three-column table:

| Mechanism | Throughput (0% loss) | Throughput (5% loss) |
|---|---|---|
| Stop-and-wait | _measured_ MB/s | _measured_ MB/s |
| Go-Back-N W=4 | _measured_ MB/s | _measured_ MB/s |
| Go-Back-N W=16 | _measured_ MB/s | _measured_ MB/s |

Add a two-paragraph analysis: why loss hurts Go-Back-N more than stop-and-wait at low window sizes, and why that changes at high window sizes.

---

## Exercises

1. **Loss injection asymmetry.** In the stop-and-wait implementation, inject loss only on ACKs (not data segments) by adding `LOSS_RATE` to the receiver's send path instead of the sender's. Does the sender behave correctly? What sequence of events occurs when an ACK is lost but the data was received? Trace through the state machine by hand and verify your code matches.

2. **Go-Back-N vs. Selective Repeat.** Modify the Go-Back-N receiver to buffer out-of-order segments (up to window size) and send individual ACKs instead of cumulative ones — this is Selective Repeat. Re-run the 5% loss benchmark for both GBN and SR with W=8. How large is the throughput difference? At what loss rate does the advantage of SR become most pronounced?

3. **Piggybacking.** In a real bidirectional protocol, ACKs are piggybacked on data segments traveling in the opposite direction. Extend `arq.py` to support bidirectional transfer where each peer simultaneously sends 50 segments and ACKs the other's segments within the same packet. The header should carry both a sequence number (for the outgoing data) and an ACK number (for incoming data).

4. **Flow control.** Add a receiver-side buffer of fixed size (e.g., 8 KB). Include the remaining buffer space as a window advertisement field in each ACK. Modify the sender to never exceed the advertised window. Observe what happens when the receiver's application layer is slow to consume delivered data — the window should shrink to zero and the sender should pause.

5. **Timer calibration.** Replace the fixed `TIMEOUT = 0.5` with Jacobson's algorithm using live RTT measurements. Sample the RTT on each non-retransmitted ACK, maintain SRTT and RTTVAR, and compute `RTO = SRTT + 4*RTTVAR` with a floor of 200ms. Verify that under `LOSS_RATE=0.0` the RTO converges to approximately twice the loopback RTT.

6. **Sequence number exhaustion.** In your Go-Back-N implementation, sequence numbers wrap modulo 256. Construct a scenario where window size W=128 causes the receiver to accept a retransmitted old segment as a new one. What is the maximum safe window size for an 8-bit sequence number field, and why does this match the textbook formula `W <= (2^n - 1) / 2`?

---

## Key Terms

| Term | Definition |
|---|---|
| **RST (TCP Reset)** | A TCP flag that abruptly closes a connection without the normal four-packet FIN sequence; accepted only if the sequence number falls within the receiver's window. |
| **Stop-and-wait ARQ** | A reliable-delivery protocol that transmits exactly one unacknowledged segment at a time, blocking until an ACK is received or the retransmission timer fires. |
| **Sliding window** | A flow-control mechanism that allows W unacknowledged segments to be in flight simultaneously, improving utilization on high-bandwidth-delay-product paths. |
| **Go-Back-N (GBN)** | A sliding-window ARQ variant where the receiver discards all out-of-order segments and the sender retransmits from the earliest unacknowledged sequence number on timeout. |
| **Selective Repeat (SR)** | A sliding-window ARQ variant where the receiver buffers out-of-order segments and the sender retransmits only the specific lost segment, requiring a larger receiver buffer than GBN. |
| **RTO (Retransmission Timeout)** | The time a TCP sender waits for an ACK before assuming the segment was lost; computed dynamically from smoothed RTT and variance estimates. |
| **Idle-timeout mismatch** | A class of outage where a load balancer or firewall silently closes idle connections at a shorter interval than the application's connection-pool keep-alive, causing RSTs on the next request. |
| **Half-open connection** | A TCP connection that appears open to one endpoint but has already been terminated (by RST, timeout, or crash) at the other; data sent into a half-open connection is met with a RST. |
| **Bandwidth-delay product** | The number of bits "in flight" on a link at any moment, equal to link capacity × round-trip propagation delay; determines the window size needed for full utilization. |
| **Alternating-bit protocol** | The simplest instance of stop-and-wait ARQ, using a 1-bit sequence number (0 or 1) to distinguish a new segment from a retransmit. |

---

## Further Reading

- **RFC 793** — *Transmission Control Protocol* (1981). The original TCP specification. Sections 3.4 (Establishing a Connection) and 3.5 (Closing a Connection) describe RST handling and the TIME_WAIT state. The sequence-number arithmetic in section 3.3 directly underlies the window-wrap exercises above.

- **Kurose & Ross, *Computer Networking: A Top-Down Approach*, 8th ed.** — Chapter 3.4 covers stop-and-wait and GBN/SR in depth with formal state-machine diagrams. The rdt3.0 finite state machine in Figure 3.15 is the direct reference for Track B Step 1.

- **Stevens, *TCP/IP Illustrated*, Vol. 1, 2nd ed.** — Chapters 13–17 cover TCP connection management, retransmission, and timeout with Wireshark-style packet traces. Chapter 18 covers TCP keep-alive, directly relevant to the idle-timeout outage.

- **Jacobson, V. (1988). "Congestion Avoidance and Control."** *ACM SIGCOMM Computer Communication Review.* The original paper introducing the RTT estimation algorithm used in Exercise 5 and the slow-start/congestion-avoidance mechanisms that build on reliable delivery.

- **Wireshark TCP Analysis documentation** — `https://wiki.wireshark.org/TCP_Analyze_Sequence_Numbers`. Explains every `tcp.analysis.*` flag (retransmission, fast retransmission, spurious retransmission, lost segment, duplicate ACK) with examples. Essential reference for Track A.
