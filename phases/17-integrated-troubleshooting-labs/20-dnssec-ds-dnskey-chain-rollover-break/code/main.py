#!/usr/bin/env python3
"""DNSSEC DS / DNSKEY chain validation and key rollover break.

Reference oracle for the integrated troubleshooting lab. Reads a
synthetic dig +dnssec +multi output (or one pasted in) and
classifies the chain. Stdlib only; no ldns.

Scenarios:

  ksk_rollover
    Child rolled the KSK; parent has not yet published the new DS.
    The chain is broken at the parent -> child step.

  algorithm_rollover
    Child rolled from RSASHA256 (8) to ECDSA P-256 (13); parent has
    DS for both algorithms during the transition. Chain is intact.

  intact
    Chain is fully validated; status is NOERROR with the AD flag.

Run:  python3 main.py --scenario ksk_rollover
      python3 main.py --scenario algorithm_rollover
      python3 main.py --scenario intact
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dnskey:
    key_tag: int
    algorithm: int
    flags: int  # 256 = ZSK, 257 = KSK
    is_ksk: bool


@dataclass(frozen=True)
class Ds:
    key_tag: int
    algorithm: int
    digest_type: int


@dataclass(frozen=True)
class Rrsig:
    type_covered: str
    signer_key_tag: int
    algorithm: int
    inception: int
    expiration: int


@dataclass(frozen=True)
class Chain:
    parent_ds: tuple[Ds, ...] = field(default_factory=tuple)
    child_dnskey: tuple[Dnskey, ...] = field(default_factory=tuple)
    child_rrsig: tuple[Rrsig, ...] = field(default_factory=tuple)


def classify(chain: Chain) -> tuple[str, str, str]:
    if not chain.parent_ds:
        return ("insecure", "no DS in parent; zone is unsigned at the parent", "no action")
    if not chain.child_dnskey:
        return ("indeterminate", "no DNSKEY returned for the child", "wait for retry or check authoritative")
    parent_tags = {ds.key_tag for ds in chain.parent_ds}
    child_ksks = [k for k in chain.child_dnskey if k.is_ksk]
    child_ksk_tags = {k.key_tag for k in child_ksks}
    if not child_ksk_tags & parent_tags:
        return (
            "bogus",
            f"parent DS key tags {sorted(parent_tags)} do not match any child KSK {sorted(child_ksk_tags)}",
            "publish the new DS in the parent; the chain is broken at DS -> DNSKEY",
        )
    now = 1_700_000_000
    for sig in chain.child_rrsig:
        if sig.expiration < now:
            return (
                "bogus",
                f"RRSIG for {sig.type_covered} expired at {sig.expiration} (now {now})",
                "re-sign the zone; the signatures have expired",
            )
    return ("secure", "chain validates; all DS match a KSK, all RRSIGs within window", "no action")


def ksk_rollover_chain() -> Chain:
    return Chain(
        parent_ds=(Ds(key_tag=12345, algorithm=8, digest_type=2),),
        child_dnskey=(
            Dnskey(key_tag=12345, algorithm=8, flags=257, is_ksk=True),
            Dnskey(key_tag=67890, algorithm=8, flags=257, is_ksk=True),
            Dnskey(key_tag=33555, algorithm=8, flags=256, is_ksk=False),
        ),
        child_rrsig=(
            Rrsig(type_covered="DNSKEY", signer_key_tag=67890, algorithm=8,
                  inception=1_699_000_000, expiration=1_703_000_000),
        ),
    )


def algorithm_rollover_chain() -> Chain:
    return Chain(
        parent_ds=(
            Ds(key_tag=12345, algorithm=8, digest_type=2),
            Ds(key_tag=22222, algorithm=13, digest_type=2),
        ),
        child_dnskey=(
            Dnskey(key_tag=12345, algorithm=8, flags=257, is_ksk=True),
            Dnskey(key_tag=22222, algorithm=13, flags=257, is_ksk=True),
            Dnskey(key_tag=33555, algorithm=8, flags=256, is_ksk=False),
            Dnskey(key_tag=33556, algorithm=13, flags=256, is_ksk=False),
        ),
        child_rrsig=(
            Rrsig(type_covered="DNSKEY", signer_key_tag=12345, algorithm=8,
                  inception=1_699_000_000, expiration=1_703_000_000),
            Rrsig(type_covered="DNSKEY", signer_key_tag=22222, algorithm=13,
                  inception=1_699_000_000, expiration=1_703_000_000),
        ),
    )


def intact_chain() -> Chain:
    return Chain(
        parent_ds=(Ds(key_tag=12345, algorithm=8, digest_type=2),),
        child_dnskey=(
            Dnskey(key_tag=12345, algorithm=8, flags=257, is_ksk=True),
            Dnskey(key_tag=33555, algorithm=8, flags=256, is_ksk=False),
        ),
        child_rrsig=(
            Rrsig(type_covered="DNSKEY", signer_key_tag=12345, algorithm=8,
                  inception=1_699_000_000, expiration=1_703_000_000),
            Rrsig(type_covered="A", signer_key_tag=33555, algorithm=8,
                  inception=1_699_000_000, expiration=1_703_000_000),
        ),
    )


def render(scenario: str, chain: Chain, status: str, reason: str, action: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"DNSSEC CHAIN VALIDATOR  --  scenario: {scenario}  verdict: {status}")
    out.append("=" * 64)
    out.append("")
    out.append("Parent DS:")
    for ds in chain.parent_ds:
        out.append(f"  key_tag={ds.key_tag} algo={ds.algorithm} digest_type={ds.digest_type}")
    out.append("")
    out.append("Child DNSKEY:")
    for k in chain.child_dnskey:
        role = "KSK" if k.is_ksk else "ZSK"
        out.append(f"  key_tag={k.key_tag} algo={k.algorithm} flags={k.flags} role={role}")
    out.append("")
    out.append("Child RRSIG (selected):")
    for s in chain.child_rrsig:
        out.append(
            f"  type_covered={s.type_covered} signer={s.signer_key_tag} algo={s.algorithm} "
            f"inception={s.inception} expiration={s.expiration}"
        )
    out.append("")
    out.append(f"Verdict : {status.upper()}")
    out.append(f"Reason  : {reason}")
    out.append(f"Action  : {action}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("ksk_rollover", "algorithm_rollover", "intact"),
        default="ksk_rollover",
    )
    args = parser.parse_args()
    chain = {
        "ksk_rollover": ksk_rollover_chain(),
        "algorithm_rollover": algorithm_rollover_chain(),
        "intact": intact_chain(),
    }[args.scenario]
    status, reason, action = classify(chain)
    print(render(args.scenario, chain, status, reason, action))


if __name__ == "__main__":
    main()
