#!/usr/bin/env python3
"""Subnetting and CIDR drill (Tanenbaum sections 5.6.2 and 5.6.3).

Stdlib only. Four interactive-ready calculators:

  1. Basic subnetting: IP + mask -> network, broadcast, host range,
     usable host count.
  2. VLSM divider: split a block (e.g. /16) into variable-sized subnets
     given a list of required host counts, producing a sorted
     allocation table.
  3. CIDR aggregation: test whether two or more adjacent prefixes can
     be combined into a supernet and produce the aggregated prefix.
  4. Practice-question generator: deterministic (seeded) problems with
     answers for drilling subnetting by hand.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional


def ip_to_int(ip: str) -> int:
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError(f"Invalid IP {ip!r}")
    val = 0
    for p in parts:
        octet = int(p)
        if octet < 0 or octet > 255:
            raise ValueError(f"Octet {p!r} out of range")
        val = (val << 8) | octet
    return val


def int_to_ip(value: int) -> str:
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def prefix_to_mask(prefix: int) -> int:
    if prefix < 0 or prefix > 32:
        raise ValueError(f"Invalid prefix /{prefix}")
    if prefix == 0:
        return 0
    return (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF


def mask_to_prefix(mask: str) -> int:
    val = ip_to_int(mask)
    if val == 0:
        return 0
    count = 0
    for i in range(31, -1, -1):
        if val & (1 << i):
            count += 1
        else:
            break
    return count


def bits_needed(hosts: int) -> int:
    if hosts < 2:
        return 0
    bits = 0
    while (1 << bits) - 2 < hosts:
        bits += 1
    return bits


@dataclass
class SubnetResult:
    cidr: str
    network: str
    broadcast: str
    first_host: str
    last_host: str
    num_hosts: int
    mask: str


def subnet(ip: str, mask_or_prefix: str) -> SubnetResult:
    if "/" in mask_or_prefix:
        prefix = int(mask_or_prefix.split("/")[1])
    else:
        prefix = mask_to_prefix(mask_or_prefix)
    ip_int = ip_to_int(ip)
    mask = prefix_to_mask(prefix)
    network = ip_int & mask
    broadcast = network | (~mask & 0xFFFFFFFF)
    if prefix < 31:
        first = network + 1
        last = broadcast - 1
        hosts = (1 << (32 - prefix)) - 2
    elif prefix == 31:
        first = network
        last = broadcast
        hosts = 2
    else:
        first = last = network
        hosts = 1
    return SubnetResult(
        cidr=f"{int_to_ip(network)}/{prefix}",
        network=int_to_ip(network),
        broadcast=int_to_ip(broadcast),
        first_host=int_to_ip(first),
        last_host=int_to_ip(last),
        num_hosts=hosts,
        mask=int_to_ip(mask),
    )


@dataclass
class VLSMAllocation:
    name: str
    required_hosts: int
    prefix: int
    network: str
    broadcast: str
    mask: str
    allocated_hosts: int


def vlsm_divide(base_cidr: str,
                requirements: list[tuple[str, int]]) -> list[VLSMAllocation]:
    base_ip, base_prefix = base_cidr.split("/")
    base_prefix = int(base_prefix)
    base_int = ip_to_int(base_ip) & prefix_to_mask(base_prefix)
    total_bits = 32 - base_prefix
    total_space = 1 << total_bits
    sorted_reqs = sorted(requirements, key=lambda x: x[1], reverse=True)
    allocations: list[VLSMAllocation] = []
    current = base_int
    for name, hosts in sorted_reqs:
        host_bits = bits_needed(hosts)
        subnet_prefix = 32 - host_bits
        subnet_size = 1 << host_bits
        if subnet_prefix < base_prefix:
            raise ValueError(f"Subnet for {name} (/ {subnet_prefix}) larger than base")
        if current + subnet_size > base_int + total_space:
            raise ValueError(f"Out of space allocating {name}")
        mask = prefix_to_mask(subnet_prefix)
        network = current
        broadcast = current + subnet_size - 1
        usable = subnet_size - 2 if subnet_prefix < 31 else subnet_size
        allocations.append(VLSMAllocation(
            name=name,
            required_hosts=hosts,
            prefix=subnet_prefix,
            network=int_to_ip(network),
            broadcast=int_to_ip(broadcast),
            mask=int_to_ip(mask),
            allocated_hosts=usable,
        ))
        current += subnet_size
    return allocations


def can_aggregate(prefix_a: str, prefix_b: str) -> Optional[str]:
    a_ip, a_p = prefix_a.split("/")
    b_ip, b_p = prefix_b.split("/")
    a_p = int(a_p)
    b_p = int(b_p)
    if a_p != b_p or a_p == 0:
        return None
    new_prefix = a_p - 1
    mask = prefix_to_mask(new_prefix)
    a_int = ip_to_int(a_ip) & mask
    b_int = ip_to_int(b_ip) & mask
    if a_int != b_int:
        return None
    return f"{int_to_ip(a_int)}/{new_prefix}"


def aggregate_list(prefixes: list[str]) -> list[str]:
    result = list(prefixes)
    changed = True
    while changed and len(result) > 1:
        changed = False
        new_result: list[str] = []
        used: set[int] = set()
        for i in range(len(result)):
            if i in used:
                continue
            merged = False
            for j in range(i + 1, len(result)):
                if j in used:
                    continue
                agg = can_aggregate(result[i], result[j])
                if agg is not None:
                    new_result.append(agg)
                    used.add(i)
                    used.add(j)
                    changed = True
                    merged = True
                    break
            if not merged and i not in used:
                new_result.append(result[i])
        result = new_result
    return result


@dataclass
class PracticeQuestion:
    question: str
    answer: str


def generate_practice(seed: int) -> list[PracticeQuestion]:
    rng = random.Random(seed)
    qs: list[PracticeQuestion] = []
    a = rng.randint(1, 223)
    b = rng.randint(0, 255)
    c = rng.randint(0, 255)
    d = rng.randint(1, 254)
    ip = f"{a}.{b}.{c}.{d}"
    prefix = rng.randint(24, 30)
    s = subnet(ip, f"/{prefix}")
    qs.append(PracticeQuestion(
        question=f"Given {ip}/{prefix}, what is the network address?",
        answer=f"Network: {s.network}  Broadcast: {s.broadcast}  "
               f"Hosts: {s.first_host} - {s.last_host}  "
               f"Usable: {s.num_hosts}",
    ))
    host_count = rng.randint(10, 500)
    bits = bits_needed(host_count)
    needed_prefix = 32 - bits
    qs.append(PracticeQuestion(
        question=f"You need a subnet for {host_count} hosts. What prefix?",
        answer=f"Need {bits} host bits -> /{needed_prefix}  "
               f"(gives {(1 << bits) - 2} usable hosts)",
    ))
    p1 = f"{rng.randint(192, 223)}.168.0.0/24"
    p2 = f"{int(p1.split('.')[0])}.168.1.0/24"
    agg = can_aggregate(p1, p2)
    qs.append(PracticeQuestion(
        question=f"Can {p1} and {p2} be aggregated? If so, what is the supernet?",
        answer=f"Aggregated: {agg}" if agg else "Not aggregatable",
    ))
    return qs


def main() -> None:
    print("=" * 64)
    print("Subnetting and CIDR Drill")
    print("=" * 64)

    print()
    print("1. Basic subnetting: IP + mask -> network/broadcast/range")
    print("-" * 64)
    tests = [
        ("192.168.1.100", "/24"),
        ("10.50.20.5", "255.255.0.0"),
        ("172.16.5.200", "/22"),
        ("192.168.100.1", "/30"),
        ("192.168.100.1", "/31"),
    ]
    for ip, m in tests:
        s = subnet(ip, m)
        print(f"  {ip:<18} {m:<16} -> network={s.network:<16} "
              f"bcast={s.broadcast:<16} hosts=[{s.first_host}..{s.last_host}] "
              f"usable={s.num_hosts}")

    print()
    print("2. VLSM: divide 172.16.0.0/16 into variable subnets")
    print("-" * 64)
    reqs = [
        ("Engineering", 500),
        ("Sales", 200),
        ("IT", 100),
        ("HR", 50),
        ("Finance", 25),
        ("Lab", 10),
    ]
    allocs = vlsm_divide("172.16.0.0/16", reqs)
    print(f"  {'Subnet':<14} {'Need':>6} {'Prefix':>8} {'Network':<18} "
          f"{'Broadcast':<18} {'Usable':>7}")
    for a in allocs:
        print(f"  {a.name:<14} {a.required_hosts:>6} /{a.prefix:<7} "
              f"{a.network:<18} {a.broadcast:<18} {a.allocated_hosts:>7}")

    print()
    print("3. CIDR aggregation")
    print("-" * 64)
    pairs = [
        ("192.168.0.0/24", "192.168.1.0/24"),
        ("192.168.0.0/24", "192.168.2.0/24"),
        ("10.0.0.0/8", "10.1.0.0/8"),
        ("172.16.0.0/20", "172.16.16.0/20"),
    ]
    for p1, p2 in pairs:
        agg = can_aggregate(p1, p2)
        print(f"  {p1:<18} + {p2:<18} -> "
              f"{agg if agg else 'NOT aggregatable'}")

    print()
    print("4. Multi-prefix aggregation")
    print("-" * 64)
    prefixes = [
        "192.168.0.0/24", "192.168.1.0/24",
        "192.168.2.0/24", "192.168.3.0/24",
    ]
    print(f"  Input: {prefixes}")
    result = aggregate_list(prefixes)
    print(f"  Aggregated: {result}")

    print()
    print("5. Practice questions (seed=42)")
    print("-" * 64)
    for q in generate_practice(42):
        print(f"  Q: {q.question}")
        print(f"  A: {q.answer}")
        print()


if __name__ == "__main__":
    main()