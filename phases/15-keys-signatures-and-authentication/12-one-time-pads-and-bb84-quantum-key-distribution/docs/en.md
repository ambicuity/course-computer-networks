# One-Time Pads and BB84 Quantum Key Distribution

> The only cipher the chapter calls *unconditionally secure* is the one-time pad: encrypt by XORing the message with a random key as long as the message, never reuse the key, and the ciphertext leaks zero information about the plaintext. The problem is distribution — how do Alice and Bob share that much secret randomness without an intruder like Trudy getting hold of it? BB84 (Bennett and Brassard, 1984) solves it with quantum mechanics: single photons polarized in one of two bases carry the bits, and any eavesdropping disturbs the photons in a way the legitimate parties can detect. This lesson implements both the pad and the protocol in pure Python. The pad simulator shows why `I love you.` and `Elvis lives` are both valid decryptions of the same ciphertext under different pads (no information in the message). The BB84 simulator walks through Alice's random bases and bits, Bob's random bases, the sifting step (Bob tells Alice which bases he used, she tells him which were right), and the eavesdropping test that detects Trudy. You will see the chapter's Fig. 8-5 reproduced end-to-end.

**Type:** Learn
**Languages:** Python, simulation
**Prerequisites:** Lessons 11 (classical ciphers), basic probability
**Time:** ~75 minutes

## Learning Objectives

- Implement a one-time pad (Vernam cipher) using XOR, and prove it is information-theoretically secure by showing every plaintext of length `n` is equally likely.
- Reproduce the chapter's `I love you.` vs `Elvis lives` example with two different pads producing the same ciphertext.
- Simulate BB84: random bases for Alice, random bases for Bob, sifting, raw key formation, and the eavesdropping check.
- Quantify the QBER (Quantum Bit Error Rate) introduced by an intercept-resend attack and explain why ~25% error rate signals tampering.
- Implement privacy amplification (squaring a block of bits) and explain why it shrinks Trudy's partial knowledge to zero.
- Articulate the practical limits of OTPs (key logistics, synchronization) and the practical limits of QKD (hardware, distance).

## The Problem

You are designing a wire between two embassies that must remain secure for thirty years. You cannot ship a DVD of key material every week; the couriers would be intercepted. Yet you cannot use AES forever — a sufficiently determined adversary will record every ciphertext and wait for a future break. What cipher protects the messages, and how do you get the key to both ends without an interceptor reading it?

The one-time pad is the answer to the first half: it is provably secure. But it requires a pre-shared random key as long as every message ever sent. BB84 is the answer to the second half: it lets Alice and Bob grow a shared random key over an optical fiber, with the property that any interception is detectable. Together they yield cryptography that does not depend on computational assumptions.

## The Concept

### The one-time pad, formalised

The pad is just XOR with a key as long as the message:

```
ciphertext[i] = plaintext[i] XOR pad[i]
plaintext[i] = ciphertext[i] XOR pad[i]
```

`XOR` is its own inverse (`a XOR a = 0`, `a XOR 0 = a`), so encryption and decryption are the same operation. The pad must be (1) truly random, (2) at least as long as the message, and (3) never reused. Any of those three failures breaks the scheme.

The chapter's example (Fig. 8-4): `I love you.` in 7-bit ASCII is `1001001 0100000 1101100 1101111 1110110 1100101 0100000 1111001 1101111 1110101 0101110`. With pad 1, the ciphertext is `0011011 1101011 0011110 0111010 0100100 0000110 0101011 1010011 0111000 0010011 0000101`. With a *different* pad 2 = `1011110 0000111 1101000 1010011 1010111 0100110 1000111 0111010 1001110 1110110 1110110`, decrypting the *same* ciphertext gives `Elvis lives`. Both plaintexts are equally plausible; the ciphertext carries zero bits of information about which one was sent.

### Information-theoretic security vs. computational security

AES, RSA, and ECC rely on **computational security**: we believe no algorithm known today can break them in feasible time, but cannot prove no future algorithm will. The one-time pad relies on **information-theoretic security**: Shannon proved in 1949 that a cipher with key as long as the message and uniformly random key gives the attacker zero distinguishing power among plaintexts of that length. The price is the key logistics.

### Why "never reuse" matters

If two messages are XORed with the same pad `K`, then `C1 XOR C2 = (P1 XOR K) XOR (P2 XOR K) = P1 XOR P2`. The key cancels; the attacker has the XOR of the two plaintexts, which is enough to recover both with statistical analysis. This is the **two-time pad attack**, and it broke Soviet spy traffic in the VENONA project in the 1940s–1980s. Modern protocols (stream ciphers in WEP, counter mode with reused nonces) collapse the same way.

### BB84: Alice, Bob, Trudy, and a photon

BB84 was published by Bennett and Brassard in 1984. Alice wants to send Bob a one-time pad. She uses **single photons** (qubits) polarized in one of two **bases**:

| Basis | 0 | 1 |
|-------|---|---|
| Rectilinear (`+`) | vertical | horizontal |
| Diagonal (`×`) | ↗ (lower-left to upper-right) | ↘ (upper-left to lower-right) |

The two bases are related by a 45° rotation. Bob also has both bases. For each bit of the pad:

1. Alice picks a random bit and a random basis, fires one photon polarized accordingly.
2. Bob picks a random basis and measures the photon.
3. If Bob picked the *correct* basis, he gets Alice's bit exactly. If he picked the *wrong* basis, the photon is randomly re-projected: he gets 0 or 1 each with 50% probability (quantum mechanics rule for a 45° rotated measurement).

After transmission, Bob announces the bases he used (in plaintext). Alice tells him which were correct. They discard the wrong-basis bits. On average **half** the bits survive — that is the sifted key.

### Trudy's dilemma

If Trudy intercepts the photon, she has the same dilemma Bob does: she does not know Alice's basis. She picks one at random, measures, and forwards a new photon polarized in the basis she used. When Bob later reports his basis and Alice confirms it, Trudy knows whether her guess was right or wrong — but she still does not know the bit when she guessed wrong. More importantly, **her measurement has perturbed the photon**: when she guesses wrong, she sends a photon in the wrong basis, which Bob will (when he happens to use Alice's original basis) read with 50% probability of being correct.

The error rate Bob sees on the sifted key is therefore:

- 0% with no eavesdropper
- ~25% with an intercept-resend attack (Trudy guesses the basis wrong half the time; when she guesses wrong, Bob gets the bit right only 50% of the time → 0.5 × 0.5 = 25%)

A measured QBER (Quantum Bit Error Rate) above ~10–15% is unambiguous evidence of eavesdropping. If Alice and Bob see such an error rate, they abort the key and try a different fiber (or call the police).

### Privacy amplification

Even if the QBER is acceptable, Trudy may have partial information. Privacy amplification transforms the sifted key into a shorter one in which Trudy's partial knowledge becomes negligible. The chapter's example: split the sifted key into blocks of 1024 bits, square each block to form a 2048-bit number, concatenate. Trudy, knowing only some input bits, cannot reproduce the squared output.

### Practical status

QKD has been demonstrated over 60 km of fiber and over free-space links to satellites (China's Micius satellite, 2017). It is not yet commodity infrastructure; the equipment is expensive, the rate is low, and the integration with classical internet protocols is still being worked out. But it is the only known method to establish a key whose security depends only on physics rather than on the difficulty of factoring or discrete logs.

## Build It

The simulator lives in `code/main.py` (≈210 lines). It exposes:

- `otp_encrypt(plaintext, pad)` and `otp_decrypt(ciphertext, pad)` — bit-level XOR.
- `text_to_bits(s)` and `bits_to_text(bits)` — ASCII (7-bit) round-trip.
- `bb84_simulate(n_bits, eavesdrop=False, seed=0)` — returns Alice's bits/bases, Bob's bits/bases, the sifted key, and the measured QBER.
- `chaperon_run(seed=42)` — reproduces the chapter's Fig. 8-5 walkthrough.
- `summarize(sifted_key)` — hex preview of the raw key.

Run the chapter's pad example:

```python
from main import otp_encrypt, text_to_bits, bits_to_text
pt = "I love you."
pad = "1010010100101111001010101010100101110001011001110111001010101110100101101001011"
bits = text_to_bits(pt)
pad_bits = [int(b) for b in pad]
ct = otp_encrypt(bits, pad_bits)
print("ciphertext bits:", "".join(str(b) for b in ct))
print("decrypts to:", bits_to_text(ct))   # I love you.
```

Run the chapter's Fig. 8-5 walkthrough:

```python
from main import chaperon_run
chaperon_run(seed=42)
```

Run a clean BB84 simulation with no eavesdropper:

```python
from main import bb84_simulate
result = bb84_simulate(1024, eavesdrop=False, seed=1)
print("Alice sifted bits:", result["alice_sifted"][:32])
print("Bob   sifted bits:", result["bob_sifted"][:32])
print("QBER:", result["qber"])
```

Run a BB84 simulation with an intercept-resend attack:

```python
result = bb84_simulate(1024, eavesdrop=True, seed=1)
print("QBER with Trudy:", result["qber"])   # ~0.25
```

Apply privacy amplification to shrink a sifted key:

```python
from main import privacy_amplify_square
result = bb84_simulate(2048, eavesdrop=True, seed=2)
amp = privacy_amplify_square(result["sifted_key"], block=64)
print("amplified key length:", len(amp))
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `otp_encrypt` / `otp_decrypt` | GCM with one-shot keys, quantum key distribution feeds | Real OTPs use hardware RNGs (ID Quantique, quantum noise diodes). |
| `bb84_simulate` | ID Quantique Cerberis, Toshiba QKD | Real systems send single photons over dedicated dark fiber at MHz rates. |
| `privacy_amplify_square` | Toeplitz hashing, universal hash families | Real implementations use Toeplitz matrices, not squaring. |
| `qber` statistic | Live QBER alarms on QKD links | Production thresholds: ~5% baseline, abort above ~11%. |
| Sifting step | Classical authenticated channel | Sifting happens after the quantum transmission, on a normal TCP/UDP channel. |

The simulator is the textbook version: deterministic, no photon physics, no fiber loss. A real QKD link must contend with detector dark counts, polarization drift, and side-channel attacks on the single-photon detectors themselves.

## Ship It

A reusable artifact for OTP and QKD demos lives at `outputs/prompt-otp-qkd.md`. It includes the chapter's pad example, a side-by-side comparison of legitimate vs intercepted BB84 runs, and a checklist for classifying observed QBER into "clean", "marginal", "compromised". Reuse it for security-team training.

## Exercises

1. Modify `otp_encrypt` to support binary string inputs (e.g. `pad="101010..."`) and verify the chapter's `Elvis lives` decrypt.
2. Implement a `two_time_pad_attack(c1, c2)` that XORs two ciphertexts encrypted with the same pad and recovers a crib from the resulting plaintext XOR.
3. Plot QBER vs eavesdropping probability for a 4096-bit BB84 run; verify it sits between 0 (no Trudy) and 0.25 (full intercept-resend).
4. Implement Toeplitz-hash privacy amplification instead of squaring and verify it produces the same effective key shrinkage.
5. Add a polarization-drift model: with probability `p_drift`, flip a transmitted bit before Bob measures. Show that small `p_drift` (1–2%) is indistinguishable from eavesdropping without further classical error correction.
6. Estimate the number of DVD-sized key deliveries per second that a 100 Gbps OTP link would require, and explain why this is impractical.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| One-time pad | "XOR with a long random key" | Information-theoretically secure *only* if the key is truly random, at least as long as the message, and never reused. |
| Unconditional security | "Cannot be broken" | Independent of computational assumptions; relies on physics or information theory. |
| Vernam cipher | "Original 1917 patent" | The XOR-based OTP. |
| BB84 | "Bennett-Brassard 1984" | Quantum key distribution using polarized photons in two bases. |
| Qubit | "Quantum bit" | A single photon whose polarization encodes 0 or 1 in some basis. |
| Basis | "Coordinate system" | Rectilinear (+) or diagonal (×); picking the wrong one randomizes the bit. |
| Sifting | "Keep only matched bases" | Alice and Bob discard ~50% of bits where their bases disagreed. |
| QBER | "Quantum Bit Error Rate" | Fraction of sifted-key bits that disagree; baseline 0–5%, alarm above 11%. |
| Intercept-resend | "Trudy measures and forwards" | The canonical QKD attack; introduces ~25% QBER. |
| Privacy amplification | "Shrink the key to wash out Trudy" | Toeplitz hashing or squaring; reduces Eve's partial knowledge to zero. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- Bennett, C. H., and Brassard, G., *Quantum cryptography: Public key distribution and coin tossing*, IEEE ICSSP, 1984.
- Scarani, V., et al., *The security of practical quantum key distribution*, Reviews of Modern Physics 81 (2009).
- Mullins, J., *Making unbreakable code*, IEEE Spectrum, May 2002.
- Shannon, C. E., *Communication Theory of Secrecy Systems*, Bell System Technical Journal 28 (1949).
- ETSI GS QKD 014 — *Quantum Key Distribution; Protocol and data format of REST-based key delivery API*.