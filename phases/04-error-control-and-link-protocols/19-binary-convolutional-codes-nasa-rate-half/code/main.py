"""NASA rate-1/2, k=7 binary convolutional code: encoder + Viterbi decoder.

Pure-stdlib implementation of the canonical CCSDS / 802.11 convolutional code
with generator polynomials g1 = 171(octal) and g2 = 133(octal). Includes a
hard-decision Viterbi decoder so you can inject errors into a codeword and
watch the maximum-likelihood path recover the original message.

Run:  python3 main.py
"""

from __future__ import annotations

from typing import List, Tuple

# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

# NASA k=7 rate-1/2 generator polynomials (octal), MSB = current input bit.
G1 = 0b1111001   # 171 octal  -> taps on input + register stages 0,1,2,5,6
G2 = 0b1011011   # 133 octal  -> taps on input + register stages 0,2,3,5
K = 7            # constraint length: 1 input + 6 memory bits
NUM_STATES = 1 << (K - 1)   # 64 states


class NASAConvolutionalCode:
    """k=7, R=1/2 binary convolutional encoder and a hard-decision Viterbi decoder."""

    def __init__(self, g1: int = G1, g2: int = G2, k: int = K) -> None:
        self.g1 = g1
        self.g2 = g2
        self.k = k
        self.n_states = 1 << (k - 1)
        self.tail_bits = k - 1
        # Precompute, for every (state, input_bit), the (next_state, output_pair).
        self._transitions = self._build_transitions()

    def _build_transitions(self) -> List[List[Tuple[int, Tuple[int, int]]]]:
        """transitions[state][input] = (next_state, (p1, p2))."""
        table: List[List[Tuple[int, Tuple[int, int]]]] = []
        for state in range(self.n_states):
            row: List[Tuple[int, Tuple[int, int]]] = []
            for bit in (0, 1):
                # Pack (input_bit, register bits) into a k-bit word, MSB = input.
                packed = (bit << (self.k - 1)) | state
                p1 = bin(packed & self.g1).count("1") & 1
                p2 = bin(packed & self.g2).count("1") & 1
                # Register shifts right: drop the LSB (oldest stage), input at MSB.
                next_state = (packed >> 1) & (self.n_states - 1)
                row.append((next_state, (p1, p2)))
            table.append(row)
        return table

    # -- encoding -----------------------------------------------------------

    def encode(self, message: List[int]) -> Tuple[List[int], List[int]]:
        """Encode a message bit list. Returns (codeword, padded_message).

        padded_message includes the k-1 zero tail bits used to flush the
        encoder back to the all-zero state, so the decoder knows where to stop.
        """
        padded = list(message) + [0] * self.tail_bits
        state = 0
        codeword: List[int] = []
        for bit in padded:
            next_state, (p1, p2) = self._transitions[state][bit]
            codeword.extend((p1, p2))
            state = next_state
        return codeword, padded

    # -- decoding -----------------------------------------------------------

    def viterbi_decode(self, received: List[int]) -> Tuple[List[int], int]:
        """Hard-decision Viterbi decoder.

        Walks the trellis keeping one survivor per state with the smallest
        accumulated Hamming distance to `received`. Returns the decoded
        message (tail bits stripped) and the final path metric (error count).
        """
        assert len(received) % 2 == 0, "received codeword must have even length"
        steps = len(received) // 2

        INF = float("inf")
        metric = [INF] * self.n_states
        metric[0] = 0  # encoder starts in the all-zero state
        backptr: List[List[int]] = []          # backptr[t][state] = chosen predecessor
        backbit: List[List[int]] = []          # backbit[t][state] = input bit of survivor

        for t in range(steps):
            r1, r2 = received[2 * t], received[2 * t + 1]
            new_metric = [INF] * self.n_states
            row_ptr: List[int] = [0] * self.n_states
            row_bit: List[int] = [0] * self.n_states
            for state in range(self.n_states):
                if metric[state] == INF:
                    continue
                for bit in (0, 1):
                    next_state, (p1, p2) = self._transitions[state][bit]
                    branch = (p1 ^ r1) + (p2 ^ r2)   # Hamming distance, 0..2
                    cand = metric[state] + branch
                    if cand < new_metric[next_state]:
                        new_metric[next_state] = cand
                        row_ptr[next_state] = state
                        row_bit[next_state] = bit
            metric = new_metric
            backptr.append(row_ptr)
            backbit.append(row_bit)

        # The terminated encoder ends in state 0 (we flushed with tail bits).
        final_state = 0
        decoded: List[int] = []
        s = final_state
        for t in range(steps - 1, -1, -1):
            decoded.append(backbit[t][s])
            s = backptr[t][s]
        decoded.reverse()
        # Strip the k-1 tail bits the encoder appended.
        message = decoded[: len(decoded) - self.tail_bits]
        return message, int(metric[final_state])


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

def _bits_to_str(bits: List[int]) -> str:
    return "".join(str(b) for b in bits)


def inject_errors(codeword: List[int], positions: List[int]) -> List[int]:
    """Return a copy of `codeword` with the bits at `positions` flipped."""
    noisy = list(codeword)
    for pos in positions:
        if 0 <= pos < len(noisy):
            noisy[pos] ^= 1
    return noisy


def run_demo(message: List[int], error_positions: List[int]) -> None:
    code = NASAConvolutionalCode()
    codeword, padded = code.encode(message)

    print("Message      :", _bits_to_str(message))
    print("Padded (+tail):", _bits_to_str(padded))
    print("Codeword     :", _bits_to_str(codeword))
    print("Codeword len :", len(codeword), "bits  (message", len(message),
          "+ tail", code.tail_bits, "-> rate 1/2)")

    noisy = inject_errors(codeword, error_positions)
    print("Noisy        :", _bits_to_str(noisy))
    print("Errors at    :", error_positions)

    decoded, metric = code.viterbi_decode(noisy)
    print("Decoded      :", _bits_to_str(decoded))
    print("Final metric :", metric, " (Hamming distance of best survivor)")
    ok = decoded == message
    print("Recovered OK :", ok)
    if not ok:
        diff = [i for i, (a, b) in enumerate(zip(message, decoded)) if a != b]
        print("Bit diffs at :", diff)


def main() -> None:
    print("=" * 64)
    print("NASA rate-1/2 k=7 convolutional code (g1=171, g2=133)")
    print("=" * 64)

    # Small worked trace matching the textbook: input 111 from state 0.
    print("\n-- Worked trace: input 1 1 1 from all-zero state --")
    code = NASAConvolutionalCode()
    state = 0
    for bit in (1, 1, 1):
        nxt, (p1, p2) = code._transitions[state][bit]
        print(f"  input {bit} | state {state:06b} -> {nxt:06b} | "
              f"emit P1={p1} P2={p2}")
        state = nxt

    # Full demo: 16-bit message, 3 injected errors (within d_free/2 = 4).
    print("\n-- Demo: 16-bit message, 3 scattered errors (should recover) --")
    msg = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1]
    run_demo(msg, error_positions=[4, 17, 31])

    # Push past the correction cliff: 6 errors -> likely decode failure.
    print("\n-- Stress: same message, 6 errors (expect failure near d_free=10) --")
    run_demo(msg, error_positions=[3, 4, 5, 6, 7, 40])

    # Burst failure mode: consecutive pair errors.
    print("\n-- Burst: 4 errors clustered in consecutive codeword pairs --")
    run_demo(msg, error_positions=[10, 11, 12, 13])


if __name__ == "__main__":
    main()
