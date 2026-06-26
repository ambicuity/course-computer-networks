"""Privacy to Freedom of Speech — Tor onion routing, wiretapping, and encryption trade-offs.

Educational simulation of how privacy technologies protect content and metadata
against different adversaries along a network path:

  1. Plain HTTP: any on-path observer sees sender, recipient, and content.
  2. TLS: an on-path wiretap sees endpoints and metadata, but not the content.
  3. Tor: layered encryption makes each relay know only its neighbors, not the
     original sender or final destination, hiding both content and most metadata.

The demo builds a Tor circuit of three volunteer relays, wraps a message in
onion layers using symmetric "keys" assigned by the client, and simulates a
passive wiretap at every hop to show what each attacker can read.

No external libraries, no network calls, no other file modifications.
Run:  python3 main.py    Exit: 0.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from enum import Enum, auto


# --------------------------------------------------------------------------- #
# Type aliases and data classes                                                #
# --------------------------------------------------------------------------- #


class Protocol(Enum):
    """Privacy protocol used for a hypothetical message."""
    PLAIN = auto()
    TLS = auto()
    TOR = auto()


@dataclass(frozen=True)
class Relay:
    """A Tor-like volunteer relay identified only by a short nickname."""
    nickname: str
    shared_key: bytes

    def peel(self, payload: bytes) -> bytes:
        """Remove this relay's onion layer (decrypt/unwrap)."""
        return _onion_decrypt(payload, self.shared_key)


@dataclass(frozen=True)
class Circuit:
    """An ordered sequence of Tor relays."""
    relays: tuple[Relay, ...]


@dataclass(frozen=True)
class Exposure:
    """What a passive observer at a given position can learn."""
    position: str
    sees_sender: bool
    sees_recipient: bool
    sees_content: bool
    sees_metadata: bool


@dataclass(frozen=True)
class LayerPrivacy:
    """Privacy at one network/OSI layer."""
    layer: str
    plain_http: str
    tls: str
    tor: str


# --------------------------------------------------------------------------- #
# Small symmetric primitives (educational stand-ins)                           #
# --------------------------------------------------------------------------- #


def _derive_stream(key: bytes, length: int) -> bytes:
    """Return a length-byte keystream derived from key via SHA-256/HMAC."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hmac.new(key, counter.to_bytes(4, "big"), hashlib.sha256).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def _onion_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Layer encryption: XOR plaintext with a key-derived stream."""
    stream = _derive_stream(key, len(plaintext))
    return bytes(b ^ s for b, s in zip(plaintext, stream))


def _onion_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """Layer decryption is identical because XOR is its own inverse."""
    return _onion_encrypt(ciphertext, key)


def _format_payload(payload: bytes) -> str:
    """Print a payload as hex or as cleartext if it looks printable."""
    try:
        text = payload.decode("utf-8")
        if text.isprintable() or text.count("\n") <= 1:
            return repr(text)
    except UnicodeDecodeError:
        pass
    return payload.hex()[:64] + ("..." if len(payload) > 32 else "")


# --------------------------------------------------------------------------- #
# Tor circuit and onion routing                                                #
# --------------------------------------------------------------------------- #


def build_circuit(relay_names: list[str]) -> Circuit:
    """Create a circuit with fresh random keys shared between client and each relay."""
    relays = tuple(
        Relay(name, secrets.token_bytes(32)) for name in relay_names
    )
    return Circuit(relays)


def wrap_onion_layers(plaintext: bytes, circuit: Circuit) -> bytes:
    """Wrap the plaintext in nested symmetric encryptions from exit to entry.

    The innermost encryption is for the exit relay; each additional relay gets
    an encryption of the previous encrypted blob. Each relay peels one layer and
    forwards the remainder, so only the exit ever sees the original plaintext.
    """
    relays = circuit.relays
    if not relays:
        raise ValueError("Circuit must contain at least one relay")

    inner = plaintext
    for relay in reversed(relays):
        inner = _onion_encrypt(inner, relay.shared_key)
    return inner


def route_through_circuit(payload: bytes, circuit: Circuit) -> bytes:
    """Simulate each relay peeling one encryption layer in order."""
    current = payload
    for relay in circuit.relays:
        current = relay.peel(current)
    return current


def describe_circuit(circuit: Circuit) -> str:
    """Return a human-readable circuit path like Alice -> Bob -> Carol."""
    return " -> ".join(relay.nickname for relay in circuit.relays)


# --------------------------------------------------------------------------- #
# Wiretap / exposure simulation                                                #
# --------------------------------------------------------------------------- #


def wiretap_plain_http(message: str, sender: str, recipient: str) -> list[Exposure]:
    """Return exposure for a plain HTTP message across a simple two-hop path."""
    return [
        Exposure("ISP (sender side)", True, True, True, True),
        Exposure("Backbone router", True, True, True, True),
        Exposure("ISP (recipient side)", True, True, True, True),
    ]


def wiretap_tls(message: str, sender: str, recipient: str) -> list[Exposure]:
    """TLS hides content but endpoints and packet metadata remain visible."""
    return [
        Exposure("ISP (sender side)", True, True, False, True),
        Exposure("Backbone router", True, True, False, True),
        Exposure("ISP (recipient side)", True, True, False, True),
    ]


def wiretap_tor(
    circuit: Circuit, sender: str, recipient: str
) -> list[tuple[str, Exposure]]:
    """Return per-relay exposure for a Tor circuit.

    The entry relay sees the sender and the middle relay, but not the content or
    final destination. The middle relay sees only its neighbors. The exit relay
    sees the middle relay, the destination, and the cleartext payload, but not
    the original sender.
    """
    n = len(circuit.relays)
    results: list[tuple[str, Exposure]] = []
    for i, relay in enumerate(circuit.relays):
        if i == 0:
            exposure = Exposure(
                f"Entry relay ({relay.nickname})",
                sees_sender=True,
                sees_recipient=False,
                sees_content=False,
                sees_metadata=True,
            )
        elif i == n - 1:
            exposure = Exposure(
                f"Exit relay ({relay.nickname})",
                sees_sender=False,
                sees_recipient=True,
                sees_content=True,
                sees_metadata=True,
            )
        else:
            exposure = Exposure(
                f"Middle relay ({relay.nickname})",
                sees_sender=False,
                sees_recipient=False,
                sees_content=False,
                sees_metadata=True,
            )
        results.append((relay.nickname, exposure))
    return results


# --------------------------------------------------------------------------- #
# Privacy layer table                                                          #
# --------------------------------------------------------------------------- #


def privacy_layer_table() -> list[LayerPrivacy]:
    """Return the classic 'privacy at each network layer' comparison."""
    return [
        LayerPrivacy(
            "Application",
            "Content fully exposed",
            "Content encrypted",
            "Content encrypted; destination hidden from most relays",
        ),
        LayerPrivacy(
            "Transport",
            "TCP ports and sizes visible",
            "TLS hides payload; ports visible",
            "TLS-like tunnels between relays; ports scrambled from observer",
        ),
        LayerPrivacy(
            "Network",
            "Source/destination IP visible",
            "Source/destination IP visible",
            "Only adjacent IPs visible to each hop",
        ),
        LayerPrivacy(
            "Link",
            "MAC addresses and metadata visible",
            "Metadata visible; payload opaque",
            "Metadata visible only to adjacent link",
        ),
        LayerPrivacy(
            "Social/Political",
            "Censorship easy; speech traceable",
            "Censorship by domain still possible",
            "Supports anonymous speech; resists blocking",
        ),
    ]


# --------------------------------------------------------------------------- #
# Output helpers                                                               #
# --------------------------------------------------------------------------- #


def _print_exposure_rows(rows: list[Exposure]) -> None:
    print(f"{'Observer':<28} {'Sender':<8} {'Recipient':<10} {'Content':<8} {'Metadata':<9}")
    print("-" * 70)
    for row in rows:
        print(
            f"{row.position:<28} "
            f"{'yes' if row.sees_sender else 'no':<8} "
            f"{'yes' if row.sees_recipient else 'no':<10} "
            f"{'yes' if row.sees_content else 'no':<8} "
            f"{'yes' if row.sees_metadata else 'no':<9}"
        )


def _print_tor_exposure(rows: list[tuple[str, Exposure]]) -> None:
    print(f"{'Observer':<28} {'Sender':<8} {'Recipient':<10} {'Content':<8} {'Metadata':<9}")
    print("-" * 70)
    for _name, exposure in rows:
        print(
            f"{exposure.position:<28} "
            f"{'yes' if exposure.sees_sender else 'no':<8} "
            f"{'yes' if exposure.sees_recipient else 'no':<10} "
            f"{'yes' if exposure.sees_content else 'no':<8} "
            f"{'yes' if exposure.sees_metadata else 'no':<9}"
        )


def _print_layer_table(rows: list[LayerPrivacy]) -> None:
    print(f"{'Layer':<18} {'Plain HTTP':<32} {'TLS':<38} {'Tor':<50}")
    print("-" * 142)
    for row in rows:
        print(
            f"{row.layer:<18} {row.plain_http:<32} {row.tls:<38} {row.tor:<50}"
        )


# --------------------------------------------------------------------------- #
# Main demonstration                                                           #
# --------------------------------------------------------------------------- #


def main() -> None:
    """Run the privacy-to-freedom-of-speech demonstration."""
    sender = "Alice"
    recipient = "Bob"
    destination = f"forum.example/user/{recipient.lower()}"
    print(f"Intended destination: {destination}")
    message = "Free speech needs private channels."
    plaintext = message.encode("utf-8")

    print("=" * 72)
    print("Privacy to Freedom of Speech")
    print("=" * 72)

    # 1. Tor onion routing demonstration.
    print("\n1. Tor onion routing")
    print("-" * 72)
    circuit = build_circuit(["EntryRelay", "MiddleRelay", "ExitRelay"])
    print(f"Circuit: {describe_circuit(circuit)}")
    print(f"Original message: {message!r}")

    onion = wrap_onion_layers(plaintext, circuit)
    print(f"\nOnion-encrypted payload leaving client: {_format_payload(onion)}")

    delivered = route_through_circuit(onion, circuit)
    print(f"Payload after exit relay peels final layer: {delivered.decode('utf-8')}")

    # 2. Wiretap visibility by hop.
    print("\n2. Wiretap scenario: what each observer sees")
    print("-" * 72)
    print("\n(a) Plain HTTP")
    _print_exposure_rows(wiretap_plain_http(message, sender, recipient))

    print("\n(b) TLS")
    _print_exposure_rows(wiretap_tls(message, sender, recipient))

    print("\n(c) Tor")
    _print_tor_exposure(wiretap_tor(circuit, sender, recipient))

    # 3. Encryption trade-offs.
    print("\n3. Encryption trade-offs")
    print("-" * 72)
    print(
        "Plain HTTP: zero protection; anyone on the path reads content, "
        "sender, recipient, and metadata."
    )
    print(
        "TLS:       content protected by end-to-end encryption, but the "
        "network still exposes source IP, destination IP, packet sizes, "
        "and timing."
    )
    print(
        "Tor:       layered encryption hides both content and routing "
        "from most observers; each relay only knows its neighbors. Cost: "
        "higher latency, lower bandwidth, exit relay still sees cleartext "
        "to the destination."
    )

    # 4. Metadata vs content exposure.
    print("\n4. Metadata vs content exposure")
    print("-" * 72)
    print(
        "Metadata (who, when, how much, to whom) often reveals more than "
        "content. TLS hides the 'what' but not the 'who' or 'when'. Tor "
        "hides most of the 'who' by routing through relays, though global "
        "adversaries observing both ends can still infer relationships via "
        "traffic analysis."
    )

    # 5. Privacy at each network layer.
    print("\n5. Privacy at each network layer")
    print("-" * 72)
    _print_layer_table(privacy_layer_table())

    # Freedom of speech closing note.
    print("\n" + "=" * 72)
    print(
        "Freedom of speech online depends on both confidentiality "
        "(encryption) and anonymity (Tor). Encryption protects the message; "
        "anonymity protects the messenger. Together they allow dissent, "
        "journalism, and personal expression even under surveillance or "
        "censorship."
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
