"""Web security threat simulator: SYN flood DoS, DDoS, and stock manipulation.

Simulates TCP SYN-flood connection-table exhaustion, multi-source
DDoS attacks, and a synthetic stock-manipulation scenario.
stdlib-only, educational — no real network calls.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConnectionSlot:
    src_ip: str
    src_port: int
    timestamp: float
    state: str = "SYN_RECEIVED"


class ConnectionTable:
    """Simulates a server's TCP connection table."""

    def __init__(self, capacity: int = 8192, timeout_s: float = 75.0):
        self.capacity = capacity
        self.timeout_s = timeout_s
        self.slots: dict[int, ConnectionSlot] = {}
        self.syn_count = 0
        self.ack_count = 0
        self.dropped = 0

    def syn(self, slot_id: int, src_ip: str, src_port: int, t: float) -> bool:
        self.syn_count += 1
        if len(self.slots) >= self.capacity:
            self.dropped += 1
            return False
        self.slots[slot_id] = ConnectionSlot(src_ip, src_port, t)
        return True

    def ack(self, slot_id: int, t: float) -> bool:
        """Complete a connection (legitimate client responds)."""
        if slot_id in self.slots:
            self.slots[slot_id].state = "ESTABLISHED"
            self.ack_count += 1
            return True
        return False

    def expire(self, t: float) -> int:
        expired = [sid for sid, s in self.slots.items()
                   if t - s.timestamp > self.timeout_s]
        for sid in expired:
            del self.slots[sid]
        return len(expired)

    def available(self) -> int:
        return self.capacity - len(self.slots)

    def established_count(self) -> int:
        return sum(1 for s in self.slots.values()
                   if s.state == "ESTABLISHED")


def simulate_syn_flood(rate_per_s: int, duration_s: int,
                      table: ConnectionTable) -> None:
    """Single-source SYN flood with forged source IPs."""
    print(f"\n[SYN Flood: {rate_per_s} SYN/s for {duration_s}s]\n")
    for t in range(duration_s):
        for i in range(rate_per_s):
            slot = t * rate_per_s + i
            forged_ip = f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"
            table.syn(slot, forged_ip, random.randint(1024, 65535), float(t))
        table.expire(float(t))
        # One legitimate connection attempt per second
        legit_ok = False
        if table.available() > 0:
            legit_slot = 10**9 + t
            table.syn(legit_slot, "192.168.1.100", 50000 + t, float(t))
            # Legitimate client completes the handshake
            table.ack(legit_slot, float(t))
            legit_ok = True
        print(f"  t={t}s: table={len(table.slots)}/{table.capacity} "
              f"avail={table.available()} legit={'OK' if legit_ok else 'BLOCKED'}")


def simulate_ddos(num_bots: int, rate_per_bot: int, duration_s: int,
                  table: ConnectionTable) -> None:
    """Multi-source DDoS from a botnet."""
    total_rate = num_bots * rate_per_bot
    print(f"\n[DDoS: {num_bots} bots x {rate_per_bot} SYN/s = {total_rate} SYN/s]\n")
    unique_sources: set[str] = set()
    for t in range(duration_s):
        for bot in range(num_bots):
            for i in range(rate_per_bot):
                slot = t * total_rate + bot * rate_per_bot + i
                bot_ip = f"172.16.{bot % 256}.{(bot * 7 + i) % 256}"
                unique_sources.add(bot_ip)
                table.syn(slot, bot_ip, random.randint(1024, 65535), float(t))
        table.expire(float(t))
        avail = table.available()
        print(f"  t={t}s: table={len(table.slots)}/{table.capacity} "
              f"avail={avail} sources={len(unique_sources)}")
        if avail <= 0:
            print("  -> Table exhausted. Legitimate connections BLOCKED.")
            break


def simulate_stock_manipulation() -> None:
    """Simulate the Emulex-style false-announcement attack."""
    print("\n[Stock Manipulation: False Announcement]\n")
    stock_price = 100.0
    shares_outstanding = 30_000_000
    market_cap = stock_price * shares_outstanding
    print(f"  Before: price=${stock_price:.2f} cap=${market_cap/1e9:.1f}B")
    print(f"  Attacker emails false press release: 'Emulex posts large loss,")
    print(f"  CEO resigning immediately.'")
    # Stock drops over a few hours
    for hour in range(1, 5):
        drop = 0.15 * (1 - hour * 0.1)  # 15% then tapering
        stock_price *= (1 - drop)
    market_cap = stock_price * shares_outstanding
    print(f"  After 4 hours: price=${stock_price:.2f} "
          f"cap=${market_cap/1e9:.1f}B")
    loss_pct = (1 - stock_price / 100.0) * 100
    print(f"  Drop: {loss_pct:.0f}%  Stockholder loss: "
          f"${30e6*(100-stock_price)/1e9:.1f}B")
    # Attacker shorts 10,000 shares at $100, covers at new price
    short_profit = 10_000 * (100 - stock_price)
    print(f"  Attacker profit (10K shares short): ${short_profit:,.0f}")


def threat_taxonomy() -> None:
    print("\n[Threat Taxonomy]\n")
    threats = [
        ("Defacement", "Page replaced", "Yahoo!, CIA, NASA, NYT",
         "Reputational", "06 (naming)"),
        ("DoS", "SYN flood", "TCP table exhaustion", "Lost business",
         "05 (threats)"),
        ("DDoS", "Botnet flood", "Hundreds of sources", "Hard to filter",
         "05 (threats)"),
        ("Data theft", "Credit card DB", "Maxim stole 300K cards", "Victim harm",
         "06 (connections)"),
        ("Stock manip.", "False release", "Emulex -60%", "$2B loss",
         "07 (mobile code)"),
        ("MITM", "Active wiretap", "Modify traffic in transit", "Credential theft",
         "06 (SSL/TLS)"),
    ]
    for name, method, example, impact, lesson in threats:
        print(f"  {name:14s} | {method:18s} | {example:25s} | {impact}")


def main() -> None:
    print("=" * 72)
    print("Web Security Threat Simulator")
    print("=" * 72)

    random.seed(42)

    # --- Single-source DoS ---
    print("\n--- Single-Source DoS ---")
    table1 = ConnectionTable(capacity=200, timeout_s=75.0)
    simulate_syn_flood(rate_per_s=500, duration_s=4, table=table1)
    print(f"\n  Total SYN: {table1.syn_count}  ACK: {table1.ack_count}  "
          f"Dropped: {table1.dropped}")

    # --- DDoS ---
    print("\n--- Distributed DoS ---")
    table2 = ConnectionTable(capacity=500, timeout_s=60.0)
    simulate_ddos(num_bots=50, rate_per_bot=20, duration_s=3, table=table2)

    # --- Stock manipulation ---
    simulate_stock_manipulation()

    # --- Taxonomy ---
    threat_taxonomy()

    # --- Three parts of web security ---
    print("\n[Three Parts of Web Security]\n")
    print("  1. Secure naming  -> Is the resource named correctly? (DNS, DNSsec)")
    print("  2. Secure connections -> Authenticated, encrypted channel (SSL/TLS)")
    print("  3. Mobile code safety -> What happens when site sends code?")

    print("\n" + "=" * 72)
    print("Summary: DoS floods tables, DDoS scales via botnets,")
    print("  stock manipulation exploits web-site trust, MITM requires line tap.")
    print("=" * 72)


if __name__ == "__main__":
    main()
