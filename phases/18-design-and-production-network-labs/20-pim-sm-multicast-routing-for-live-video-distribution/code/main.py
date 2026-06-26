"""PIM-SM Multicast Design Planner.

Plans a Protocol Independent Multicast Sparse Mode (PIM-SM) domain for an
enterprise live video distribution fabric. The planner is fully offline: it
takes a static inventory, runs the RFC 5059 BSR hash function, computes an
SPT-switchover threshold, and emits a design report plus vendor-specific
config snippets. Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

GROUP_RANGE_START = 0xEF102000  # 239.16.32.0
GROUP_RANGE_MASK = 24
ANYCAST_RP_LOOPBACK = "10.255.255.1/32"
PIM_SSM_BOUNDARY = "232.16.32.0/24"
SOURCE_LOOPBACK = "10.100.0.50/32"
HASH_MASK_LEN = 30
SPT_KBPS = 1000
SPT_SECONDS = 100
SPT_GRACE_SECONDS = 60
PER_RECEIVER_MBPS = 25.0
SITE_COUNT = 28
LONG_HAUL_COST_FACTOR = 1.0  # dollars per Mbps per month, normalized


@dataclass(frozen=True)
class Rpcandidate:
    """A physical RP candidate with its BSR priority and region tag."""

    name: str
    address: str
    priority: int
    region: str
    role: str  # "primary" or "secondary" within the region


@dataclass(frozen=True)
class Site:
    """A receiver site in the inventory."""

    name: str
    region: str
    receivers: int
    l2_device: str
    l3_device: str


@dataclass(frozen=True)
class Receiver:
    """A single receiver endpoint."""

    site: str
    igmp_version: int
    group: str
    bitrate_kbps: int


@dataclass
class DesignReport:
    """Output container for the planner."""

    rp_set: list[tuple[str, str, int, str]] = field(default_factory=list)
    spt_threshold_s: int = 0
    spt_threshold_kbps: int = 0
    rpt_bandwidth_mbps: float = 0.0
    spt_bandwidth_mbps: float = 0.0
    savings_mbps: float = 0.0
    outputs: dict[str, str] = field(default_factory=dict)


def bsr_hash(group_ip: str, candidates: list[Rpcandidate], hash_mask_len: int) -> int:
    """RFC 5059 BSR hash function.

    Returns the index into the candidate list that wins the hash for the
    given group. The hash is ``((G hash-mask) + (M hash-mask)) mod 2^31 mod N``
    where G is the group IP as a 32-bit integer and M is the hash-mask.
    """

    octets = [int(x) for x in group_ip.split(".")]
    g = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
    mask = (0xFFFFFFFF << (32 - hash_mask_len)) & 0xFFFFFFFF
    g_masked = g & mask
    m_masked = mask
    combined = (g_masked + m_masked) & 0x7FFFFFFF
    n = len(candidates)
    return combined % n


def highest_priority_winner(group: str, candidates: list[Rpcandidate]) -> Rpcandidate:
    """Among ties on hash index, return the highest-priority candidate."""

    idx = bsr_hash(group, candidates, HASH_MASK_LEN)
    primary = candidates[idx]
    tied = [c for c in candidates if c.priority == primary.priority]
    if len(tied) > 1:
        tied.sort(key=lambda c: c.address)
        return tied[0]
    return primary


def iter_groups(start: int, mask: int) -> Iterable[int]:
    """Yield every group IP integer in the range."""

    host_bits = 32 - mask
    for i in range(1 << host_bits):
        yield start + i


def int_to_ip(value: int) -> str:
    """Convert a 32-bit integer to a dotted-quad string."""

    return f"{(value >> 24) & 0xFF}.{(value >> 16) & 0xFF}.{(value >> 8) & 0xFF}.{value & 0xFF}"


def build_inventory() -> tuple[list[Rpcandidate], list[Site], list[Receiver]]:
    """Construct a representative inventory for the design report."""

    rps = [
        Rpcandidate("rp-dc1-1", "10.255.0.1/32", priority=200, region="dc1", role="primary"),
        Rpcandidate("rp-dc1-2", "10.255.0.2/32", priority=192, region="dc1", role="secondary"),
        Rpcandidate("rp-dc2-1", "10.255.0.3/32", priority=180, region="dc2", role="primary"),
        Rpcandidate("rp-dc2-2", "10.255.0.4/32", priority=170, region="dc2", role="secondary"),
        Rpcandidate("rp-dc3-1", "10.255.0.5/32", priority=160, region="dc3", role="primary"),
        Rpcandidate("rp-dc3-2", "10.255.0.6/32", priority=150, region="dc3", role="secondary"),
    ]
    sites = [
        Site(
            name=f"site-{i:02d}",
            region=("dc1" if i < 10 else "dc2" if i < 20 else "dc3"),
            receivers=120 + (i * 3) % 50,
            l2_device="Catalyst 9300-48UXM",
            l3_device=(
                "MX204"
                if i >= 10 and i < 20
                else "7800R3"
                if i >= 20
                else "Catalyst 9500-48Y4C"
            ),
        )
        for i in range(SITE_COUNT)
    ]
    receivers = [
        Receiver(
            site=s.name,
            igmp_version=3 if i % 5 else 2,
            group="239.16.32.100",
            bitrate_kbps=int(PER_RECEIVER_MBPS * 1000),
        )
        for i, s in enumerate(sites)
    ]
    return rps, sites, receivers


def render_cisco(rps: list[Rpcandidate], sites: list[Site]) -> str:
    """Render an IOS XE 17.12 configuration block."""

    lines = [
        "! Cisco IOS XE 17.12 - PIM-SM and Anycast-RP",
        "! Catalyst 9500 / Nexus 9300 family",
        "ip multicast-routing distributed",
        f"ip pim rp-address {ANYCAST_RP_LOOPBACK.split('/')[0]} 239.16.32.0/24",
        "!",
        "! Candidate BSR / RP (highest priority on the elected primary)",
        f"ip pim bsr-candidate Loopback0 {HASH_MASK_LEN} 255",
        "ip pim rp-candidate Loopback0 group-list MULTICAST-RANGE interval 60",
        "!",
        "! MSDP mesh between physical RPs",
    ]
    seen: set[str] = set()
    for rp in rps:
        if rp.address in seen:
            continue
        seen.add(rp.address)
        for peer in rps:
            if peer.address == rp.address:
                continue
            lines.append(
                f"ip msdp peer {peer.address.split('/')[0]} connect-source Loopback0 remote-as 65000"
            )
            lines.append(f"ip msdp password peer-{peer.address.split('/')[0]} 7 070C285F4D06")
    lines.extend([
        "!",
        "! IGMP/MLD snooping - querier on the L3 gateway",
        "ip igmp snooping vlan 100-250 querier address 10.10.0.1",
        "ip igmp snooping vlan 100-250 immediate-leave",
        "!",
        "! SPT switchover threshold - keep on RPT for the first 60 s",
        "ip pim spt-threshold 1000 100 group-list MULTICAST-RANGE",
        "!",
        "! PIM-SSM boundary for inter-DC replication",
        f"ip pim ssm range {PIM_SSM_BOUNDARY}",
        "!",
        "ip access-list standard MULTICAST-RANGE",
        " permit 239.16.32.0 0.0.0.255",
    ])
    return "\n".join(lines) + "\n"


def render_juniper(rps: list[Rpcandidate]) -> str:
    """Render a Junos 22.4R3 configuration block."""

    lines = [
        "# Juniper Junos 22.4R3 - PIM-SM and Anycast-RP",
        "# MX204 family",
        "set protocols pim rp static address 10.255.255.1 group-ranges 239.16.32.0/24",
        "set protocols pim rp static address 10.100.0.50 group-ranges 232.16.32.0/24",
        "set protocols pim interface all mode sparse",
        "set protocols pim interface lo0.0 mode sparse",
    ]
    for rp in rps:
        if "dc1" not in rp.region:
            continue
        lines.append(
            f"set protocols pim rp local address {rp.address.split('/')[0]} override"
        )
    for rp in rps:
        for peer in rps:
            if peer.name == rp.name:
                continue
            lines.append(
                f"set protocols msdp peer {peer.address.split('/')[0]} "
                f"local-address {rp.address.split('/')[0]}"
            )
    lines.extend([
        "set protocols msdp group 239.16.32.0/24 mode inclusive",
        f"set protocols pim spt-threshold interval {SPT_SECONDS} bytes {SPT_KBPS * 1000}",
        f"set protocols pim ssm-groups {PIM_SSM_BOUNDARY}",
    ])
    return "\n".join(lines) + "\n"


def render_arista(rps: list[Rpcandidate]) -> str:
    """Render an Arista EOS 4.30 configuration block."""

    lines = [
        "! Arista EOS 4.30 - PIM-SM and Anycast-RP",
        "! 7800R3 family",
        "router pim",
        "  rp-address 10.255.255.1 group-list 239.16.32.0/24",
        "  rp-address 10.100.0.50 group-list 232.16.32.0/24",
        f"  ssm range {PIM_SSM_BOUNDARY}",
    ]
    for rp in rps:
        if "dc3" not in rp.region:
            continue
        lines.append(
            f"  rp-candidate {rp.address.split('/')[0]} group-list 239.16.32.0/24 "
            f"priority {rp.priority} interval 60"
        )
    lines.append("  bsr candidate loopback0 hash-mask-length 30 priority 255")
    for rp in rps:
        for peer in rps:
            if peer.name == rp.name:
                continue
            lines.append(
                f"  msdp peer {peer.address.split('/')[0]} local-interface Loopback0"
            )
    return "\n".join(lines) + "\n"


def compute_bandwidth(receivers: list[Receiver]) -> tuple[float, float]:
    """Return (RPT bandwidth in Mbps, SPT bandwidth in Mbps)."""

    total_receivers = max(1, sum(1 for _ in receivers))
    # RPT: one copy per site (one per last-hop router with receivers)
    rpt_mbps = PER_RECEIVER_MBPS * SITE_COUNT
    # SPT: one copy per distinct source-path; assume grouping by /32 source
    spt_mbps = PER_RECEIVER_MBPS * max(1, total_receivers // 1000)
    return rpt_mbps, spt_mbps


def write_outputs(
    out_dir: Path,
    rps: list[Rpcandidate],
    sites: list[Site],
    receivers: list[Receiver],
) -> DesignReport:
    """Render all output artifacts to disk and return a summary report."""

    out_dir.mkdir(parents=True, exist_ok=True)
    report = DesignReport(spt_threshold_kbps=SPT_KBPS, spt_threshold_s=SPT_SECONDS)
    rpt, spt = compute_bandwidth(receivers)
    report.rpt_bandwidth_mbps = rpt
    report.spt_bandwidth_mbps = spt
    report.savings_mbps = max(0.0, rpt - spt)
    sorted_rps = sorted(rps, key=lambda c: -c.priority)
    rp_lines = [
        "group,primary_rp,primary_addr,backup_rp,backup_addr,priority,hash_index",
    ]
    for g_int in list(iter_groups(GROUP_RANGE_START, GROUP_RANGE_MASK))[:16]:
        g = int_to_ip(g_int)
        primary = highest_priority_winner(g, sorted_rps)
        backup_pool = [c for c in sorted_rps if c.address != primary.address]
        backup = highest_priority_winner(g, backup_pool)
        idx = bsr_hash(g, sorted_rps, HASH_MASK_LEN)
        rp_lines.append(
            f"{g},{primary.name},{primary.address},{backup.name},{backup.address},"
            f"{primary.priority},{idx}"
        )
        report.rp_set.append((g, primary.name, primary.priority, backup.name))
    (out_dir / "rp-set.txt").write_text("\n".join(rp_lines) + "\n", encoding="utf-8")
    (out_dir / "cisco-ios-xe.conf").write_text(render_cisco(rps, sites), encoding="utf-8")
    (out_dir / "juniper-junos.conf").write_text(render_juniper(rps), encoding="utf-8")
    (out_dir / "arista-eos.conf").write_text(render_arista(rps), encoding="utf-8")
    md = [
        "# BSR / RP Design Report",
        "",
        f"- Group range: `239.16.32.0/{GROUP_RANGE_MASK}`",
        f"- Anycast-RP: `{ANYCAST_RP_LOOPBACK}`",
        f"- Physical RPs: {len(rps)}",
        f"- BSR hash-mask: {HASH_MASK_LEN}",
        f"- SPT switchover: {SPT_KBPS} kbps for {SPT_SECONDS} s (grace {SPT_GRACE_SECONDS} s)",
        f"- RPT bandwidth estimate: {rpt:.1f} Mbps",
        f"- SPT bandwidth estimate: {spt:.1f} Mbps",
        f"- Estimated savings: {report.savings_mbps:.1f} Mbps",
        "",
        "## RP-to-group mapping (first 16 groups)",
        "",
        "| Group | Primary RP | Priority | Backup RP |",
        "|-------|------------|----------|-----------|",
    ]
    for g, primary, priority, backup in report.rp_set:
        md.append(f"| {g} | {primary} | {priority} | {backup} |")
    (out_dir / "bsr-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    report.outputs = {
        "rp-set": str(out_dir / "rp-set.txt"),
        "cisco": str(out_dir / "cisco-ios-xe.conf"),
        "juniper": str(out_dir / "juniper-junos.conf"),
        "arista": str(out_dir / "arista-eos.conf"),
        "report": str(out_dir / "bsr-report.md"),
    }
    return report


def main() -> None:
    """Run the planner and print the design report."""

    rps, sites, receivers = build_inventory()
    out_dir = Path(__file__).resolve().parent.parent / "outputs"
    report = write_outputs(out_dir, rps, sites, receivers)
    print("=== GlobalCorp PIM-SM Design Report ===")
    print(f"Group range: 239.16.32.0/{GROUP_RANGE_MASK}")
    print(f"Active groups: {len(report.rp_set)}")
    print(f"Anycast-RP: {ANYCAST_RP_LOOPBACK}")
    print(f"Physical RPs: {len(rps)} (DC1x2, DC2x2, DC3x2)")
    print(f"BSR hash-mask: {HASH_MASK_LEN}")
    sample = report.rp_set[0]
    print(f"Hash winner for 239.16.32.100 -> {sample[1]} priority {sample[2]}")
    print(f"SPT-switchover: {report.spt_threshold_s} s / {report.spt_threshold_kbps} kbps")
    print(f"PIM-SSM boundary: {PIM_SSM_BOUNDARY} source {SOURCE_LOOPBACK}")
    print(f"Total RPT bandwidth: {report.rpt_bandwidth_mbps:.2f} Gbps (estimated)")
    print(f"Total SPT bandwidth (post-switchover): {report.spt_bandwidth_mbps:.2f} Gbps")
    pct = (report.savings_mbps / report.rpt_bandwidth_mbps * 100) if report.rpt_bandwidth_mbps else 0
    print(f"Savings: {report.savings_mbps * 1000:.0f} Mbps / ~{pct:.0f}% reduction on long-haul")
    print("\nOutputs:")
    for label, path in report.outputs.items():
        print(f"  [{label}] {path}")


if __name__ == "__main__":
    main()
