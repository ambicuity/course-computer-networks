# Regulating the Sending Rate: AIMD and cwnd

> The textbook reduces congestion control to two questions: *what signal does the network give the sender* and *what control law should the sender use to react*? Signals come in four flavors captured in Fig. 6-23: explicit & precise (XCP), explicit & imprecise (TCP with ECN), implicit & precise (FAST TCP using delay), and implicit & imprecise (classic CUBIC TCP and TCP using packet loss). The control law is **AIMD** — Additive Increase, Multiplicative Decrease — the only combination of the four pure policies that converges to the fair-and-efficient operating point from any starting allocation. Chiu and Jain's 1989 graphical argument plots user 1's bandwidth on the x-axis and user 2's on the y-axis, draws a fairness line `x = y` and an efficiency line `x + y = 100%`, and shows that additive-additive oscillates along a 45-degree line, multiplicative-multiplicative oscillates along a line through the origin, and only AIMD marches straight to the intersection. TCP implements AIMD indirectly by adjusting a sliding window `cwnd` (congestion window); the equivalent sending rate is `cwnd / RTT`. This lesson walks through the four signal types, the Chiu-Jain convergence proof, and runs an AIMD simulation that reproduces the textbook Fig. 6-25 trajectory.

**Type:** Learn
**Languages:** Python, simulation traces
**Prerequisites:** Desirable bandwidth allocation (Phase 10 lesson 11), feedback control basics, cwnd and RTT concepts
**Time:** ~80 minutes

## Learning Objectives

- Classify congestion control signals along the *explicit/implicit* and *precise/imprecise* axes, naming a representative protocol for each of the four cells.
- Draw the Chiu-Jain fairness/efficiency diagram and explain why AIMD converges to the optimal operating point while AIAD, MIMD, and MIAD do not.
- Express the TCP equivalent sending rate as `cwnd / RTT` and explain why adjusting a window is preferred to pacing at a fixed rate.
- Implement a two-flow AIMD simulator and watch the `(x_1, x_2)` trajectory spiral into the optimal point from a corner of the allocation space.
- Distinguish classic AIMD-Reno (cwnd += 1 per RTT, halve on triple-dup-ACK) from AIMD-Tahoe (cwnd -> 1 on any loss) and from CUBIC's time-since-loss cubic.
- Explain why AIMD has an intrinsic RTT bias: connections to closer peers get more bandwidth, all else equal, and name the protocol extensions (CUBIC, BBR) that try to fix this.

## The Problem

A network engineer tunes two TCP senders sharing a 100 Mbps link. The two flows settle into a 50/50 split most of the time, but every minute or so one of them briefly starves the other; the average throughput oscillates, and the Wireshark graph shows sawtooth-shaped cwnd curves that look identical but with different slopes. The engineer asks: *is the sawtooth inevitable? Could we double the link capacity and have both flows double their throughput? Why does it always settle at 50/50 and not 60/40?*

The answer to all three is AIMD, and the *why* is the Chiu-Jain 1989 result. The Chiu-Jain proof is unusual for networking: it is a graphical argument that fits in a 2x2 plane and shows that of the four possible control laws, only one converges from anywhere. The simulated `code/main.py` reproduces the proof by stepping two flows through repeated AIMD rounds and plotting their `(x_1, x_2)` trajectory, which spirals into the optimal point.

## The Concept

### The four signal types (Fig. 6-23)

Different network layers give different kinds of feedback, and the textbook organizes them by two axes: explicit vs implicit, precise vs imprecise.

| Signal | Explicit? | Precise? | Example |
|--------|-----------|----------|---------|
| Rate to use | yes | yes | XCP (Katabi 2002) |
| Congestion warning | yes | no | TCP with ECN (RFC 3168) |
| End-to-end delay | no | yes | FAST TCP (Wei 2006) |
| Packet loss & delay | no | yes | Compound TCP (Windows, Tan 2006) |
| Packet loss | no | no | classic TCP, CUBIC (Linux default) |

A precise signal tells the sender *how much* to slow down; an imprecise signal only says "slow down" without a target. An explicit signal is a deliberate network-layer message; an implicit signal is something the sender infers (loss, delay, jitter). The classic Internet, with drop-tail or RED routers, gives the sender only packet loss, which is implicit and imprecise. That is the regime in which AIMD's `loss -> halve cwnd` rule is appropriate.

### The Chiu-Jain control-law argument

Chiu and Jain's 1989 paper reduces the question to a 2D plane. Let user 1's bandwidth be `x_1` and user 2's be `x_2`. The fairness line is `x_1 = x_2` (the diagonal from origin to `(100%, 100%)`); the efficiency line is `x_1 + x_2 = 100%` (the line from `(100%, 0%)` to `(0%, 100%)`). The optimal point is the intersection `(50%, 50%)`. The network signals congestion when the sum `x_1 + x_2` exceeds 100%; otherwise it stays silent.

A *control law* is a pair of response curves: one for what to do when no signal arrives (the "increase" policy) and one for what to do when a signal arrives (the "decrease" policy). Chiu and Jain considered four: additive increase, multiplicative increase, additive decrease, multiplicative decrease. There are four combinations:

- **AIA D** (additive increase, additive decrease): the trajectory follows a 45-degree line. After a congestion signal, both users reduce by the same amount, so the line goes `(50+a, 50+a) -> (50+a-d, 50+a-d)`, still on the same line. The trajectory stays on a line of slope 1; it oscillates but does not converge to fairness.
- **MIMD** (multiplicative increase, multiplicative decrease): the trajectory follows a line through the origin. The sum `x_1 + x_2` shrinks proportionally each round; if it is above 100% it shrinks, if below 100% it grows. The line still passes through the origin, so the trajectory never hits the fairness line unless it started there.
- **MAID / AIAD** (mixed): only one of the two policies is multiplicative. Chiu and Jain showed these diverge from the optimal point.
- **AIMD** (additive increase, multiplicative decrease): the trajectory follows a 45-degree line during the increase phase (additive moves along `(x_1 + a, x_2 + a)`), and a line through the origin during the decrease phase (multiplicative moves along `(x_1 * b, x_2 * b)` with `b < 1`). The combination makes the trajectory spiral into the optimal point: after the additive step, the operating point is closer to the fairness line, and after the multiplicative step, the operating point is closer to the efficiency line. Repeating these two steps makes the trajectory contract toward the intersection.

The argument is intuitive: a multiplicative decrease preserves the *ratio* of the two users' bandwidths (the point moves along a line through the origin), so if the ratio is wrong (one user is unfairly favored) it stays wrong. The next additive increase moves along a 45-degree line, which *changes* the ratio by giving each user the same increment. The two phases together bring the trajectory closer to fairness and to efficiency, while the other three combinations fail to address one of the two goals.

### TCP implements AIMD via cwnd

TCP does not have an API to set a sending rate directly; it has a *congestion window* `cwnd` that bounds how many unacknowledged bytes may be in flight. The sender paces at roughly `cwnd / RTT` bytes per second (the actual rate depends on the ACK clock). The AIMD control law becomes:

- On every successful RTT (no loss): `cwnd += MSS` (additive increase, typically 1 MSS per RTT for Reno, more for CUBIC).
- On a loss event (triple-duplicate ACK for Reno, or timeout for Tahoe): `cwnd *= beta` (multiplicative decrease, typically `beta = 0.5` for Reno, so cwnd halves).

This is a *window-based* AIMD, not a *rate-based* one. The textbook highlights a subtle but important point: the additive increase is "1 MSS per RTT," not "1 Mbps per second." A connection with a 200 ms RTT takes 200 ms to gain 1 MSS; a connection with a 20 ms RTT takes 20 ms to gain 1 MSS. The long-RTT connection grows 10x more slowly — that is the **RTT bias** the textbook calls out, and it is why CUBIC (lesson 23) decouples the growth function from RTT.

### Why a window and not a rate?

A rate-based protocol would need a precise internal clock and would have to ask the network for feedback. Window-based AIMD piggybacks on the ACK clock: the sender transmits up to `cwnd` bytes, and the rate emerges naturally from the rate at which ACKs return. If the network drops packets, ACKs stop returning, and the sender slows down *automatically* in one RTT — no need for a separate pacing clock, no need for explicit rate feedback. The window is also a natural way to combine congestion control with flow control: the effective window is `min(cwnd, rwnd)`, where `rwnd` is the receiver-advertised window.

### The four pure policies and their divergence

To see why the other three combinations fail, consider MIAD (multiplicative increase, additive decrease). Multiplicative increase moves along a line through the origin and grows the sum `x_1 + x_2`. Additive decrease then subtracts a constant from both. After enough rounds, the trajectory escapes the efficiency line entirely — one user's share can grow without bound, which is the textbook's "diverges from the optimal point" claim. Similarly, MIMD with a small `beta` (e.g. `beta = 0.1`) underutilizes the link; the multiplicative decrease is so aggressive that the trajectory never reaches 100% utilization. AIMD is the unique combination that converges to the *intersection* of fairness and efficiency, which is the engineering argument that has anchored TCP congestion control for thirty-five years.

## Build It

`code/main.py` simulates the Chiu-Jain trajectory for two flows sharing a 100-unit link. Each round, both flows additively increase (`a = 1`), the simulator checks whether `x_1 + x_2 > 100`, and if so both flows multiplicatively decrease (`beta = 0.5`). The script prints the trajectory and verifies that successive rounds bring `(x_1, x_2)` arbitrarily close to `(50, 50)`.

The simulation is a small class with three methods: `step()` (one round), `run(n)` (n rounds), and `report()` (textual summary). All state is local to the simulator instance. Run it with `python3 code/main.py`.

## Use It

| Function | Input | Output | When to use |
|----------|-------|--------|-------------|
| `AIMDSimulator` | initial `(x_1, x_2)`, capacity, `a`, `beta` | a simulator with `.step()` and `.run()` | exploring AIMD convergence from any starting point |
| `sim.step()` | none | updated `(x_1, x_2)` after one round | running a single add-then-maybe-decrease cycle |
| `sim.run(n)` | number of rounds | list of `(x_1, x_2)` snapshots | observing the trajectory over many rounds |
| `verify_chiu_jain()` | none | a printed trajectory that converges to `(50, 50)` | sanity-checking against the textbook Fig. 6-25 |

The `verify_chiu_jain()` helper starts the two flows at `(95, 5)` and `(5, 95)` and shows both trajectories converging to `(50, 50)` within ~10 rounds.

## Ship It

A runnable Python script that simulates the AIMD control law. Run `python3 code/main.py` and observe the trajectory from various starting points converging to the optimal operating point.

| File | What it contains |
|------|------------------|
| `docs/en.md` | This lesson |
| `code/main.py` | AIMD simulator and Chiu-Jain convergence verification |
| `assets/regulating-the-sending-rate-aimd-and-cwnd.svg` | The four signal types, the fairness/efficiency diagram, and the AIMD spiral trajectory |

## Exercises

1. Run `python3 code/main.py` and observe the trajectory of two flows starting at `(95, 5)`. How many rounds does it take to reach within 1.0 of `(50, 50)`?
2. Repeat the simulation with `a = 5` (faster additive increase). Does the trajectory still converge? Is the path smoother or rougher?
3. Try `beta = 0.9` (mild multiplicative decrease). Comment on whether the trajectory is still stable and whether it reaches the optimal point.
4. Plot the trajectory for the corner start `(99, 1)` for 30 rounds. What is the maximum overshoot below `(50, 50)` along the way?
5. Implement an `MIMDSimulator` and start it from `(50, 50)`. Verify that it stays on the line through the origin and never reaches fairness.
6. Why does a connection with a 200 ms RTT gain bandwidth more slowly than a connection with a 20 ms RTT under classic AIMD-Reno? Which modern TCP variant fixes this bias?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| AIMD | Additive Increase Multiplicative Decrease | The unique control law that converges to the fair-and-efficient operating point from any starting allocation |
| Chiu-Jain result | "AIMD is the only convergent control law" | The 1989 graphical proof that of the four pure policies, only AIMD marches into the intersection of fairness and efficiency |
| cwnd | Congestion window | The TCP sender's bound on bytes in flight; rate is `cwnd / RTT` |
| rwnd | Receiver window | The receiver-advertised flow-control bound; effective window is `min(cwnd, rwnd)` |
| MSS | Maximum segment size | The largest TCP segment the sender will emit; AIMD grows cwnd in units of MSS |
| ECN | Explicit Congestion Notification | An explicit-but-imprecise signal: routers mark a bit, sender halves cwnd |
| XCP | eXplicit Control Protocol | An explicit-and-precise signal: routers tell senders the rate to use |
| FAST TCP | Delay-based congestion control | Uses round-trip delay as the signal; precise but implicit |
| CUBIC | Cubic growth function | The Linux default; growth is a function of time since the last loss, not RTT |
| RTT bias | "Long-haul TCP gets less bandwidth" | The intrinsic unfairness of per-RTT additive increase; close peers grow faster |
| ACK clock | "Packets are paced by ACKs" | The transmission rhythm produced by returning acknowledgements; window-based AIMD uses it instead of a real-time clock |

## Further Reading

- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., §6.3.2 ("Regulating the Sending Rate") — the textbook chapter for this lesson.
- Chiu, D.-M. & Jain, R., "Analysis of the increase/decrease algorithms for congestion avoidance in computer networks," *Journal of Computer Networks and ISDN Systems*, 1989. The original AIMD convergence proof.
- Jacobson, V., "Congestion avoidance and control," *SIGCOMM '88*. The paper that introduced AIMD into TCP and coined "congestion collapse."
- Floyd, S., Henderson, T. & Gurtov, A., "The NewReno Modification to TCP's Fast Recovery Algorithm," RFC 6582, 2012.
- Ramakrishnan, K., Floyd, S. & Black, D., "The Addition of Explicit Congestion Notification (ECN) to IP," RFC 3168, 2001.
- Katabi, D., Handley, M. & Rohrs, C., "Internet Congestion Control for High Bandwidth-Delay Product Networks," *SIGCOMM '02* (XCP).
- Ha, S., Rhee, I. & Xu, L., "CUBIC: A New TCP-Friendly High-Speed TCP Variant," *ACM SIGOPS Operating Systems Review*, 2008.
- Wei, D. X. et al., "FAST TCP: Motivation, Architecture, Algorithms, Performance," *IEEE/ACM TON*, 2006.
- Tan, K. et al., "A Compound TCP Approach for High-Speed and Long Distance Networks," *INFOCOM 2006*.
