#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Site:
    name: str
    asn: int | None
    ospf_area: str | None
    block: str
    snmpv3: bool
    syslog_server: str | None
    ntp_server: str | None
    on_call_contacts: int


@dataclass(frozen=True)
class Vlan:
    site: str
    vlan_id: int
    name: str
    subnet: str
    category: str
    vrrp: bool
    dot1x: bool
    dscp_policy: str | None
    dhcp_snooping: bool
    dai: bool
    acl: bool
    zone: str


@dataclass(frozen=True)
class WanLink:
    name: str
    site_a: str
    site_b: str
    transit_subnet: str
    protocol: str
    qos_policy: bool
    bfd: bool


@dataclass(frozen=True)
class BgpSession:
    local_asn: int
    peer_asn: int
    peer_ip: str
    local_pref: int
    as_path_prepend: int
    inbound_filter: bool
    outbound_filter: bool
    bfd: bool


@dataclass(frozen=True)
class OspfArea:
    area_id: str
    site: str
    is_stub: bool
    abr_count: int


@dataclass(frozen=True)
class QosClass:
    name: str
    dscp: str
    queue_type: str
    bw_pct: int


@dataclass(frozen=True)
class Alert:
    signal: str
    threshold: str
    runbook: str


@dataclass(frozen=True)
class VrrpPair:
    site: str
    vlan_id: int
    vip: str
    master: str
    backup: str
    bfd: bool
    preempt_delay_s: int


@dataclass
class Finding:
    category: str
    check: str
    status: str
    score: int
    detail: str
    remediation: str


SITES = [
    Site("HQ-Austin", 65001, "0", "10.10.0.0/22", True, "10.10.40.10", "10.10.40.11", 3),
    Site("Branch-A-Denver", None, "1", "10.20.0.0/22", True, "10.10.40.10", "10.10.40.11", 2),
    Site("Branch-B-Charlotte", None, "2", "10.30.0.0/22", True, "10.10.40.10", "10.10.40.11", 1),
    Site("Cloud-VPC-us-east-1", None, None, "10.40.0.0/16", True, "10.10.40.10", "pool.ntp.org", 2),
]

VLANS: list[Vlan] = [
    Vlan("HQ-Austin", 10, "user-data", "10.10.10.0/24", "user_data", True, True, "AF21", True, True, True, "user"),
    Vlan("HQ-Austin", 20, "voice", "10.10.20.0/24", "voice", True, True, "EF", True, True, True, "user"),
    Vlan("HQ-Austin", 30, "video", "10.10.30.0/24", "video", True, True, "AF41", True, True, True, "user"),
    Vlan("HQ-Austin", 40, "server", "10.10.40.0/24", "server", True, False, "AF21", True, True, True, "server"),
    Vlan("HQ-Austin", 50, "printer", "10.10.50.0/24", "printer", False, False, None, True, True, True, "user"),
    Vlan("HQ-Austin", 99, "mgmt", "10.10.99.0/24", "mgmt", True, False, None, True, True, True, "mgmt"),
    Vlan("Branch-A-Denver", 110, "user-data", "10.20.10.0/24", "user_data", True, True, "AF21", True, True, True, "user"),
    Vlan("Branch-A-Denver", 120, "voice", "10.20.20.0/24", "voice", True, True, "EF", True, True, True, "user"),
    Vlan("Branch-A-Denver", 130, "video", "10.20.30.0/24", "video", True, True, "AF41", True, True, True, "user"),
    Vlan("Branch-A-Denver", 199, "mgmt", "10.20.99.0/24", "mgmt", True, False, None, True, True, True, "mgmt"),
    Vlan("Branch-B-Charlotte", 210, "user-data", "10.30.10.0/24", "user_data", True, True, "AF21", True, True, True, "user"),
    Vlan("Branch-B-Charlotte", 220, "voice", "10.30.20.0/24", "voice", True, True, "EF", True, True, True, "user"),
    Vlan("Branch-B-Charlotte", 230, "video", "10.30.30.0/24", "video", True, False, "AF41", True, True, True, "user"),
    Vlan("Branch-B-Charlotte", 299, "mgmt", "10.30.99.0/24", "mgmt", True, False, None, True, True, True, "mgmt"),
    Vlan("Cloud-VPC-us-east-1", 401, "app", "10.40.10.0/24", "server", False, False, "AF21", False, False, True, "cloud"),
    Vlan("Cloud-VPC-us-east-1", 402, "db", "10.40.20.0/24", "server", False, False, "AF21", False, False, True, "cloud"),
    Vlan("Cloud-VPC-us-east-1", 499, "mgmt", "10.40.99.0/24", "mgmt", False, False, None, False, False, True, "mgmt"),
]

WAN_LINKS: list[WanLink] = [
    WanLink("HQ-ISP1", "HQ-Austin", "ISP-1", "172.16.1.0/30", "ebgp", True, True),
    WanLink("HQ-ISP2", "HQ-Austin", "ISP-2", "172.16.2.0/30", "ebgp", True, True),
    WanLink("HQ-Denver", "HQ-Austin", "Branch-A-Denver", "172.16.10.0/30", "ospf", True, True),
    WanLink("HQ-Charlotte", "HQ-Austin", "Branch-B-Charlotte", "172.16.20.0/30", "ospf", True, True),
    WanLink("HQ-Cloud", "HQ-Austin", "Cloud-VPC-us-east-1", "172.16.30.0/30", "ibgp", False, False),
]

BGP_SESSIONS: list[BgpSession] = [
    BgpSession(65001, 64512, "172.16.1.2", 200, 0, True, True, True),
    BgpSession(65001, 64513, "172.16.2.2", 100, 3, True, True, True),
]

OSPF_AREAS: list[OspfArea] = [
    OspfArea("0", "HQ-Austin", False, 2),
    OspfArea("1", "Branch-A-Denver", True, 1),
    OspfArea("2", "Branch-B-Charlotte", True, 1),
]

QOS_CLASSES: list[QosClass] = [
    QosClass("voice", "EF", "LLQ", 20),
    QosClass("video", "AF41", "CBWFQ", 30),
    QosClass("signaling", "CS3", "CBWFQ", 5),
    QosClass("business", "AF21", "CBWFQ", 25),
    QosClass("default", "BE", "WFQ", 20),
    QosClass("scavenger", "CS1", "DROP", 0),
]

ALERTS: list[Alert] = [
    Alert("bgp_session_change", "state != Established", "runbooks/bgp-flap-response.md"),
    Alert("vrrp_state_change", "master_down_event", "runbooks/vrrp-failover.md"),
    Alert("ospf_neighbor_loss", "neighbor_state != Full", "runbooks/ospf-neighbor-loss.md"),
    Alert("wan_utilization", "util_pct > 85 for 10m", "runbooks/wan-saturation.md"),
    Alert("interface_error_rate", "error_rate_pct > 0.1 for 5m", "runbooks/interface-errors.md"),
]

VRRP_PAIRS: list[VrrpPair] = [
    VrrpPair("HQ-Austin", 10, "10.10.10.1", "Core-A", "Core-B", True, 10),
    VrrpPair("HQ-Austin", 20, "10.10.20.1", "Core-B", "Core-A", True, 10),
    VrrpPair("HQ-Austin", 30, "10.10.30.1", "Core-A", "Core-B", True, 10),
    VrrpPair("HQ-Austin", 40, "10.10.40.1", "Core-B", "Core-A", True, 10),
    VrrpPair("HQ-Austin", 99, "10.10.99.254", "Core-A", "Core-B", True, 10),
    VrrpPair("Branch-A-Denver", 110, "10.20.10.1", "BR-A-Sw1", "BR-A-Sw2", True, 10),
    VrrpPair("Branch-A-Denver", 120, "10.20.20.1", "BR-A-Sw2", "BR-A-Sw1", True, 10),
    VrrpPair("Branch-A-Denver", 130, "10.20.30.1", "BR-A-Sw1", "BR-A-Sw2", True, 10),
    VrrpPair("Branch-A-Denver", 199, "10.20.99.254", "BR-A-Sw1", "BR-A-Sw2", True, 10),
    VrrpPair("Branch-B-Charlotte", 210, "10.30.10.1", "BR-B-Sw1", "BR-B-Sw2", True, 10),
    VrrpPair("Branch-B-Charlotte", 220, "10.30.20.1", "BR-B-Sw2", "BR-B-Sw1", True, 10),
    VrrpPair("Branch-B-Charlotte", 230, "10.30.30.1", "BR-B-Sw1", "BR-B-Sw2", True, 10),
    VrrpPair("Branch-B-Charlotte", 299, "10.30.99.254", "BR-B-Sw1", "BR-B-Sw2", True, 10),
]

CAT_ADDR = "Addressing and Segmentation"
CAT_ROUT = "Routing and Redundancy"
CAT_SEC  = "Security Baseline"
CAT_QOS  = "QoS and Application Delivery"
CAT_MON  = "Monitoring and Operations"


def _pass(cat: str, check: str, detail: str) -> Finding:
    return Finding(cat, check, "PASS", 10, detail, "")


def _warn(cat: str, check: str, detail: str, remediation: str) -> Finding:
    return Finding(cat, check, "WARN", 6, detail, remediation)


def _fail(cat: str, check: str, detail: str, remediation: str) -> Finding:
    return Finding(cat, check, "FAIL", 0, detail, remediation)


def check_addressing(vlans: list[Vlan], wan_links: list[WanLink], sites: list[Site]) -> list[Finding]:
    findings: list[Finding] = []

    all_subnets = [v.subnet for v in vlans] + [w.transit_subnet for w in wan_links]
    nets = [ipaddress.ip_network(s, strict=True) for s in all_subnets]
    overlaps = [
        f"{nets[i]} ↔ {nets[j]}"
        for i in range(len(nets))
        for j in range(i + 1, len(nets))
        if nets[i].overlaps(nets[j])
    ]
    if overlaps:
        findings.append(_fail(CAT_ADDR, "No subnet overlaps",
                              f"{len(overlaps)} overlap(s): {'; '.join(overlaps[:2])}",
                              "Renumber overlapping subnets using the hierarchical addressing plan"))
    else:
        findings.append(_pass(CAT_ADDR, "No subnet overlaps",
                              f"{len(nets)} subnets checked — no overlaps detected"))

    enterprise_net = ipaddress.ip_network("10.0.0.0/8")
    non_enterprise = [v.subnet for v in vlans if not ipaddress.ip_network(v.subnet, strict=True).subnet_of(enterprise_net)]
    if non_enterprise:
        findings.append(_fail(CAT_ADDR, "All VLAN subnets within 10.0.0.0/8",
                              f"Non-conforming: {', '.join(non_enterprise)}",
                              "Move non-conforming subnets into the 10.0.0.0/8 aggregate"))
    else:
        findings.append(_pass(CAT_ADDR, "All VLAN subnets within 10.0.0.0/8",
                              f"All {len(vlans)} VLAN subnets are within 10.0.0.0/8"))

    phys_vlans = [v for v in vlans if v.site != "Cloud-VPC-us-east-1"]
    vlan_ids = [v.vlan_id for v in phys_vlans]
    dupes = [vid for vid in set(vlan_ids) if vlan_ids.count(vid) > 1]
    if dupes:
        findings.append(_warn(CAT_ADDR, "VLAN IDs globally unique across physical sites",
                              f"Duplicate VLAN IDs: {dupes}",
                              "Renumber duplicate VLANs using site-offset scheme (site × 100 + function)"))
    else:
        findings.append(_pass(CAT_ADDR, "VLAN IDs globally unique across physical sites",
                              f"{len(set(vlan_ids))} distinct VLAN IDs across {len(phys_vlans)} physical VLANs"))

    phys_sites = [s for s in sites if s.ospf_area is not None]
    sites_with_mgmt = {v.site for v in vlans if v.category == "mgmt" and v.site != "Cloud-VPC-us-east-1"}
    missing_mgmt = [s.name for s in phys_sites if s.name not in sites_with_mgmt]
    if missing_mgmt:
        findings.append(_fail(CAT_ADDR, "Management VLAN at every physical site",
                              f"Missing mgmt VLAN at: {', '.join(missing_mgmt)}",
                              "Provision a dedicated management VLAN (99x series) at each site"))
    else:
        findings.append(_pass(CAT_ADDR, "Management VLAN at every physical site",
                              f"Mgmt VLAN present at all {len(phys_sites)} physical sites"))

    vlan1_users = [v for v in vlans if v.vlan_id == 1]
    if vlan1_users:
        findings.append(_fail(CAT_ADDR, "No production use of default VLAN 1",
                              f"VLAN 1 in use at: {[v.site for v in vlan1_users]}",
                              "Reassign all ports off VLAN 1 and configure 'switchport trunk native vlan <unused>'"))
    else:
        findings.append(_pass(CAT_ADDR, "No production use of default VLAN 1",
                              "VLAN 1 not used for production traffic at any site"))

    oversized = [v.subnet for v in vlans if ipaddress.ip_network(v.subnet, strict=True).prefixlen < 24]
    if oversized:
        findings.append(_warn(CAT_ADDR, "All VLAN subnets /24 or smaller",
                              f"Oversized allocations: {', '.join(oversized)}",
                              "Sub-allocate large subnets to match actual host counts (max /24 per VLAN)"))
    else:
        findings.append(_pass(CAT_ADDR, "All VLAN subnets /24 or smaller",
                              "All VLAN subnets are /24 — efficient allocation confirmed"))

    user_subnets = {v.subnet for v in vlans if v.zone == "user"}
    server_subnets = {v.subnet for v in vlans if v.zone == "server"}
    if user_subnets & server_subnets:
        findings.append(_fail(CAT_ADDR, "Server zone subnet separate from user zone",
                              "User and server subnets overlap — zone boundary is undefined",
                              "Move server VLANs to a dedicated server zone subnet"))
    else:
        findings.append(_pass(CAT_ADDR, "Server zone subnet separate from user zone",
                              f"{len(server_subnets)} server subnet(s) fully isolated from {len(user_subnets)} user subnet(s)"))

    cloud_block = next((s.block for s in sites if "Cloud" in s.name), None)
    site_blocks = [s.block for s in sites if "Cloud" not in s.name and s.block]
    if cloud_block:
        cloud_net = ipaddress.ip_network(cloud_block, strict=True)
        conflicts = [b for b in site_blocks if ipaddress.ip_network(b, strict=True).overlaps(cloud_net)]
        if conflicts:
            findings.append(_fail(CAT_ADDR, "Cloud VPC block non-overlapping with enterprise sites",
                                  f"Cloud {cloud_block} overlaps: {', '.join(conflicts)}",
                                  "Re-allocate cloud VPC to a distinct /16 within 10.0.0.0/8"))
        else:
            findings.append(_pass(CAT_ADDR, "Cloud VPC block non-overlapping with enterprise sites",
                                  f"Cloud {cloud_block} does not overlap any of {len(site_blocks)} site blocks"))

    return findings


def check_routing(ospf_areas: list[OspfArea], bgp_sessions: list[BgpSession]) -> list[Finding]:
    findings: list[Finding] = []

    backbone = [a for a in ospf_areas if a.area_id == "0"]
    if not backbone or backbone[0].abr_count < 2:
        abr_count = backbone[0].abr_count if backbone else 0
        findings.append(_fail(CAT_ROUT, "OSPF Area 0 has at least 2 ABRs",
                              f"Area 0 has {abr_count} ABR(s) — single ABR is a single point of failure",
                              "Add a second ABR (Core-B) and redistribute OSPF routes through both"))
    else:
        findings.append(_pass(CAT_ROUT, "OSPF Area 0 has at least 2 ABRs",
                              f"Area 0 has {backbone[0].abr_count} ABRs at HQ"))

    non_backbone = [a for a in ospf_areas if a.area_id != "0"]
    non_stub = [a for a in non_backbone if not a.is_stub]
    if non_stub:
        findings.append(_fail(CAT_ROUT, "Branch OSPF areas are stub type",
                              f"Non-stub branch areas: {[a.area_id for a in non_stub]}",
                              "Configure 'area X stub' on branch routers to suppress external LSA flooding"))
    else:
        findings.append(_pass(CAT_ROUT, "Branch OSPF areas are stub type",
                              f"All {len(non_backbone)} branch area(s) are stub — external LSAs suppressed"))

    peer_asns = [s.peer_asn for s in bgp_sessions]
    if len(set(peer_asns)) < 2:
        findings.append(_fail(CAT_ROUT, "BGP dual-homed to two distinct upstream ASNs",
                              f"Only {len(set(peer_asns))} distinct peer ASN(s) configured",
                              "Establish eBGP session to a second upstream ISP with a different ASN"))
    else:
        findings.append(_pass(CAT_ROUT, "BGP dual-homed to two distinct upstream ASNs",
                              f"eBGP sessions to ASN {peer_asns[0]} and ASN {peer_asns[1]}"))

    missing_inbound = [s for s in bgp_sessions if not s.inbound_filter]
    if missing_inbound:
        findings.append(_fail(CAT_ROUT, "BGP inbound prefix filter on all sessions",
                              f"No inbound filter on session(s) to: {[s.peer_ip for s in missing_inbound]}",
                              "Apply inbound prefix-list to all eBGP sessions — deny RFC-1918 and default route"))
    else:
        findings.append(_pass(CAT_ROUT, "BGP inbound prefix filter on all sessions",
                              f"Inbound prefix filter applied to all {len(bgp_sessions)} BGP sessions"))

    missing_outbound = [s for s in bgp_sessions if not s.outbound_filter]
    if missing_outbound:
        findings.append(_fail(CAT_ROUT, "BGP outbound prefix filter on all sessions",
                              f"No outbound filter on session(s) to: {[s.peer_ip for s in missing_outbound]}",
                              "Apply outbound prefix-list — only announce registered enterprise prefixes"))
    else:
        findings.append(_pass(CAT_ROUT, "BGP outbound prefix filter on all sessions",
                              f"Outbound prefix filter applied to all {len(bgp_sessions)} BGP sessions"))

    primary = [s for s in bgp_sessions if s.local_pref == max(s.local_pref for s in bgp_sessions)]
    secondary = [s for s in bgp_sessions if s.local_pref < max(s.local_pref for s in bgp_sessions)]
    if not secondary or secondary[0].as_path_prepend == 0:
        findings.append(_warn(CAT_ROUT, "AS-path prepend on secondary ISP for inbound traffic preference",
                              "Secondary ISP has no AS-path prepend — upstream providers treat both paths equally",
                              "Add 'set as-path prepend 65001 65001 65001' to the route-map applied to ISP-2 outbound"))
    else:
        findings.append(_pass(CAT_ROUT, "AS-path prepend on secondary ISP for inbound traffic preference",
                              f"Secondary ISP (ASN {secondary[0].peer_asn}) has {secondary[0].as_path_prepend}× prepend"))

    missing_bfd = [s for s in bgp_sessions if not s.bfd]
    if missing_bfd:
        findings.append(_warn(CAT_ROUT, "BFD enabled on all BGP sessions",
                              f"BFD missing on {len(missing_bfd)} session(s)",
                              "Enable BFD with 300 ms interval on all eBGP sessions to reduce failover to < 1 s"))
    else:
        findings.append(_pass(CAT_ROUT, "BFD enabled on all BGP sessions",
                              f"BFD active on all {len(bgp_sessions)} BGP sessions — sub-second failover capable"))

    high_pref = max(s.local_pref for s in bgp_sessions) if bgp_sessions else 0
    low_pref = min(s.local_pref for s in bgp_sessions) if bgp_sessions else 0
    if high_pref <= low_pref:
        findings.append(_fail(CAT_ROUT, "LOCAL_PREF asymmetry enforces primary ISP preference for outbound",
                              f"All sessions have identical LOCAL_PREF {high_pref}",
                              "Set LOCAL_PREF 200 for ISP-1 and LOCAL_PREF 100 for ISP-2 on inbound route-maps"))
    else:
        findings.append(_pass(CAT_ROUT, "LOCAL_PREF asymmetry enforces primary ISP preference for outbound",
                              f"LOCAL_PREF {high_pref} (primary) vs {low_pref} (secondary) — deterministic outbound path"))

    return findings


def check_redundancy(vrrp_pairs: list[VrrpPair], vlans: list[Vlan], wan_links: list[WanLink]) -> list[Finding]:
    findings: list[Finding] = []

    user_vlans = [v for v in vlans if v.category in ("user_data", "voice", "video")]
    vrrp_covered = {(p.site, p.vlan_id) for p in vrrp_pairs}
    missing_vrrp = [(v.site, v.vlan_id, v.name) for v in user_vlans
                    if (v.site, v.vlan_id) not in vrrp_covered and not v.vrrp]
    uncovered = [v for v in user_vlans if not v.vrrp]
    if uncovered:
        findings.append(_warn(CAT_ROUT, "VRRP on all user-facing VLANs (data, voice, video)",
                              f"VRRP missing on {len(uncovered)} user VLAN(s): "
                              f"{[(v.site, v.vlan_id) for v in uncovered]}",
                              "Configure VRRP on all user VLANs — a missing VRRP gateway means single-device dependency"))
    else:
        findings.append(_pass(CAT_ROUT, "VRRP on all user-facing VLANs (data, voice, video)",
                              f"VRRP configured on all {len(user_vlans)} user VLAN(s)"))

    bad_pairs = [p for p in vrrp_pairs if p.master == p.backup]
    if bad_pairs:
        findings.append(_fail(CAT_ROUT, "VRRP master and backup are distinct devices",
                              f"{len(bad_pairs)} pair(s) with identical master and backup",
                              "Assign VRRP master and backup to different physical switches"))
    else:
        findings.append(_pass(CAT_ROUT, "VRRP master and backup are distinct devices",
                              f"All {len(vrrp_pairs)} VRRP pair(s) use distinct master/backup devices"))

    missing_bfd_vrrp = [p for p in vrrp_pairs if not p.bfd]
    if missing_bfd_vrrp:
        findings.append(_warn(CAT_ROUT, "BFD tracking on VRRP uplink interfaces",
                              f"BFD missing on {len(missing_bfd_vrrp)} VRRP pair(s)",
                              "Configure BFD with 300 ms interval on uplinks tracked by VRRP priority decrement"))
    else:
        findings.append(_pass(CAT_ROUT, "BFD tracking on VRRP uplink interfaces",
                              f"BFD active on all {len(vrrp_pairs)} VRRP pair(s) — sub-3 s failover capable"))

    ebgp_links = [w for w in wan_links if w.protocol == "ebgp"]
    if len(ebgp_links) < 2:
        findings.append(_fail(CAT_ROUT, "Dual WAN uplinks at HQ (two ISP circuits)",
                              f"Only {len(ebgp_links)} eBGP WAN link(s) — single ISP is a single point of failure",
                              "Provision and configure eBGP to a second ISP"))
    else:
        findings.append(_pass(CAT_ROUT, "Dual WAN uplinks at HQ (two ISP circuits)",
                              f"{len(ebgp_links)} eBGP uplinks — dual ISP path redundancy confirmed"))

    return findings


def check_security(vlans: list[Vlan]) -> list[Finding]:
    findings: list[Finding] = []

    user_data_vlans = [v for v in vlans if v.category == "user_data"]
    no_dot1x_data = [v for v in user_data_vlans if not v.dot1x]
    if no_dot1x_data:
        findings.append(_fail(CAT_SEC, "802.1X on all user-data VLANs",
                              f"No 802.1X on {len(no_dot1x_data)} data VLAN(s): "
                              f"{[(v.site, v.vlan_id) for v in no_dot1x_data]}",
                              "Enable 802.1X EAP-TLS with RADIUS on all user-data VLANs"))
    else:
        findings.append(_pass(CAT_SEC, "802.1X on all user-data VLANs",
                              f"802.1X enforced on all {len(user_data_vlans)} user-data VLAN(s)"))

    voice_vlans = [v for v in vlans if v.category == "voice"]
    no_dot1x_voice = [v for v in voice_vlans if not v.dot1x]
    if no_dot1x_voice:
        findings.append(_warn(CAT_SEC, "802.1X or MAC-bypass auth on all voice VLANs",
                              f"No auth policy on {len(no_dot1x_voice)} voice VLAN(s): "
                              f"{[(v.site, v.vlan_id) for v in no_dot1x_voice]}",
                              "Configure MAC authentication bypass (MAB) with phone RADIUS policy on voice VLANs"))
    else:
        findings.append(_pass(CAT_SEC, "802.1X or MAC-bypass auth on all voice VLANs",
                              f"Auth policy enforced on all {len(voice_vlans)} voice VLAN(s)"))

    video_vlans = [v for v in vlans if v.category == "video"]
    no_dot1x_video = [v for v in video_vlans if not v.dot1x]
    if no_dot1x_video:
        findings.append(_warn(CAT_SEC, "802.1X on all video VLANs",
                              f"No 802.1X on {len(no_dot1x_video)} video VLAN(s): "
                              f"{[(v.site, v.vlan_id) for v in no_dot1x_video]}",
                              "Enable 802.1X EAP-TLS on video VLANs — endpoint validation prevents rogue devices"))
    else:
        findings.append(_pass(CAT_SEC, "802.1X on all video VLANs",
                              f"802.1X enforced on all {len(video_vlans)} video VLAN(s)"))

    access_vlans = [v for v in vlans if v.category in ("user_data", "voice", "video", "printer")]
    no_dhcp_snoop = [v for v in access_vlans if not v.dhcp_snooping]
    if no_dhcp_snoop:
        findings.append(_fail(CAT_SEC, "DHCP snooping on all access VLANs",
                              f"DHCP snooping missing on {len(no_dhcp_snoop)} VLAN(s)",
                              "Enable 'ip dhcp snooping vlan X' and mark uplinks as trusted"))
    else:
        findings.append(_pass(CAT_SEC, "DHCP snooping on all access VLANs",
                              f"DHCP snooping active on all {len(access_vlans)} access VLAN(s)"))

    no_dai = [v for v in access_vlans if not v.dai]
    if no_dai:
        findings.append(_fail(CAT_SEC, "Dynamic ARP Inspection on all access VLANs",
                              f"DAI missing on {len(no_dai)} VLAN(s)",
                              "Enable 'ip arp inspection vlan X' — requires DHCP snooping binding table"))
    else:
        findings.append(_pass(CAT_SEC, "Dynamic ARP Inspection on all access VLANs",
                              f"DAI active on all {len(access_vlans)} access VLAN(s)"))

    no_acl = [v for v in vlans if not v.acl]
    if no_acl:
        findings.append(_fail(CAT_SEC, "ACL on all inter-zone VLAN interfaces",
                              f"No ACL on {len(no_acl)} VLAN(s): {[(v.site, v.vlan_id) for v in no_acl]}",
                              "Apply inbound ACL on every SVI — default deny inter-zone, explicit permit for known flows"))
    else:
        findings.append(_pass(CAT_SEC, "ACL on all inter-zone VLAN interfaces",
                              f"ACL applied to all {len(vlans)} VLAN SVI(s)"))

    mgmt_user_overlap = [v for v in vlans if v.zone == "mgmt" and v.category == "user_data"]
    if mgmt_user_overlap:
        findings.append(_fail(CAT_SEC, "Management VLAN isolated from user VLANs",
                              "Management VLAN incorrectly categorised as user zone",
                              "Move management VLAN to dedicated OOB segment — no user reachability"))
    else:
        findings.append(_pass(CAT_SEC, "Management VLAN isolated from user VLANs",
                              "All mgmt VLANs are in zone 'mgmt' — OOB isolation confirmed"))

    server_vlans = [v for v in vlans if v.category == "server" and v.site != "Cloud-VPC-us-east-1"]
    unprotected_server = [v for v in server_vlans if not v.acl]
    if unprotected_server:
        findings.append(_fail(CAT_SEC, "Server zone ACL with explicit deny-default",
                              f"No ACL on {len(unprotected_server)} server VLAN(s)",
                              "Apply explicit ACL permitting only known ports (443, 22 with MFA) from known source zones"))
    else:
        findings.append(_pass(CAT_SEC, "Server zone ACL with explicit deny-default",
                              f"Server zone protected by ACL on all {len(server_vlans)} server VLAN(s)"))

    sites_without_snmpv3 = [s for s in SITES if not s.snmpv3]
    if sites_without_snmpv3:
        findings.append(_fail(CAT_SEC, "SNMPv3 only — no SNMPv1/v2c community strings",
                              f"SNMPv3 not confirmed at: {[s.name for s in sites_without_snmpv3]}",
                              "Configure SNMPv3 with SHA auth and AES-128 priv; remove all community strings"))
    else:
        findings.append(_pass(CAT_SEC, "SNMPv3 only — no SNMPv1/v2c community strings",
                              f"SNMPv3 enforced at all {len(SITES)} sites"))

    printer_vlans = [v for v in vlans if v.category == "printer"]
    no_port_sec = [v for v in printer_vlans if not v.dhcp_snooping]
    if no_port_sec:
        findings.append(_warn(CAT_SEC, "Port security controls on printer and IoT VLANs",
                              f"Missing controls on {len(no_port_sec)} printer VLAN(s)",
                              "Enable MAC limit (max 1 MAC per port) and sticky MAC on printer access ports"))
    else:
        findings.append(_pass(CAT_SEC, "Port security controls on printer and IoT VLANs",
                              f"DHCP snooping and DAI applied to all {len(printer_vlans)} printer VLAN(s)"))

    return findings


def check_qos(vlans: list[Vlan], qos_classes: list[QosClass], wan_links: list[WanLink]) -> list[Finding]:
    findings: list[Finding] = []

    voice_vlans = [v for v in vlans if v.category == "voice"]
    bad_voice = [v for v in voice_vlans if v.dscp_policy != "EF"]
    if bad_voice:
        findings.append(_fail(CAT_QOS, "Voice VLANs marked DSCP EF",
                              f"{len(bad_voice)} voice VLAN(s) not marked EF: "
                              f"{[(v.site, v.dscp_policy) for v in bad_voice]}",
                              "Configure 'set dscp ef' on voice VLAN ingress policy-map"))
    else:
        findings.append(_pass(CAT_QOS, "Voice VLANs marked DSCP EF",
                              f"All {len(voice_vlans)} voice VLAN(s) correctly marked DSCP EF"))

    video_vlans = [v for v in vlans if v.category == "video"]
    bad_video = [v for v in video_vlans if v.dscp_policy != "AF41"]
    if bad_video:
        findings.append(_fail(CAT_QOS, "Video VLANs marked DSCP AF41",
                              f"{len(bad_video)} video VLAN(s) not marked AF41",
                              "Configure 'set dscp af41' on video VLAN ingress policy-map"))
    else:
        findings.append(_pass(CAT_QOS, "Video VLANs marked DSCP AF41",
                              f"All {len(video_vlans)} video VLAN(s) correctly marked DSCP AF41"))

    llq = [c for c in qos_classes if c.queue_type == "LLQ" and c.bw_pct > 0]
    if not llq:
        findings.append(_fail(CAT_QOS, "LLQ priority queue defined for voice",
                              "No LLQ class found with non-zero bandwidth guarantee",
                              "Add 'priority percent 20' to the voice class in the egress policy-map"))
    else:
        findings.append(_pass(CAT_QOS, "LLQ priority queue defined for voice",
                              f"LLQ class '{llq[0].name}' at {llq[0].bw_pct}% bandwidth guarantee"))

    cbwfq = [c for c in qos_classes if c.queue_type == "CBWFQ" and c.dscp == "AF41"]
    if not cbwfq:
        findings.append(_fail(CAT_QOS, "CBWFQ class defined for video traffic",
                              "No CBWFQ class matched to DSCP AF41",
                              "Add 'bandwidth percent 30' to the video class in the egress policy-map"))
    else:
        findings.append(_pass(CAT_QOS, "CBWFQ class defined for video traffic",
                              f"CBWFQ class '{cbwfq[0].name}' at {cbwfq[0].bw_pct}%"))

    scavenger = [c for c in qos_classes if c.queue_type == "DROP" and c.bw_pct == 0]
    if not scavenger:
        findings.append(_warn(CAT_QOS, "Scavenger class defined with zero bandwidth guarantee",
                              "No DROP class found — bulk P2P traffic competes with business traffic",
                              "Add a scavenger class matching DSCP CS1 with 'police rate 1 mbps'"))
    else:
        findings.append(_pass(CAT_QOS, "Scavenger class defined with zero bandwidth guarantee",
                              f"Scavenger class '{scavenger[0].name}' policed to zero guaranteed bandwidth"))

    wan_without_qos = [w for w in wan_links if not w.qos_policy]
    if wan_without_qos:
        findings.append(_warn(CAT_QOS, "QoS policy applied to all WAN links",
                              f"{len(wan_without_qos)} WAN link(s) without QoS: "
                              f"{[w.name for w in wan_without_qos]}",
                              "Apply egress policy-map with LLQ/CBWFQ to all WAN-facing interfaces"))
    else:
        findings.append(_pass(CAT_QOS, "QoS policy applied to all WAN links",
                              f"QoS policy applied to all {len(wan_links)} WAN link(s)"))

    return findings


def check_monitoring(sites: list[Site], alerts: list[Alert]) -> list[Finding]:
    findings: list[Finding] = []

    no_snmp = [s for s in sites if not s.snmpv3]
    if no_snmp:
        findings.append(_fail(CAT_MON, "SNMPv3 enabled at all sites",
                              f"SNMPv3 missing at: {[s.name for s in no_snmp]}",
                              "Configure SNMPv3 engine, user, and access on all managed devices"))
    else:
        findings.append(_pass(CAT_MON, "SNMPv3 enabled at all sites",
                              f"SNMPv3 active at all {len(sites)} sites"))

    no_syslog = [s for s in sites if not s.syslog_server]
    if no_syslog:
        findings.append(_fail(CAT_MON, "Centralized syslog configured at all sites",
                              f"No syslog server at: {[s.name for s in no_syslog]}",
                              "Configure 'logging host <collector>' on all devices; use TCP 514 for reliability"))
    else:
        findings.append(_pass(CAT_MON, "Centralized syslog configured at all sites",
                              f"All {len(sites)} sites ship syslog to {sites[0].syslog_server}"))

    no_ntp = [s for s in sites if not s.ntp_server]
    if no_ntp:
        findings.append(_fail(CAT_MON, "NTP synchronized at all sites",
                              f"No NTP server at: {[s.name for s in no_ntp]}",
                              "Configure 'ntp server <stratum2-source>' — unsynced clocks break log correlation"))
    else:
        findings.append(_pass(CAT_MON, "NTP synchronized at all sites",
                              f"NTP configured at all {len(sites)} sites"))

    required_signals = {"bgp_session_change", "vrrp_state_change", "ospf_neighbor_loss",
                        "wan_utilization", "interface_error_rate"}
    defined_signals = {a.signal for a in alerts}
    missing_signals = required_signals - defined_signals
    if missing_signals:
        findings.append(_fail(CAT_MON, "BGP/VRRP/OSPF/WAN alerts defined",
                              f"Missing alert signal(s): {', '.join(sorted(missing_signals))}",
                              "Define alert rules for each missing signal in the monitoring stack"))
    else:
        findings.append(_pass(CAT_MON, "BGP/VRRP/OSPF/WAN alerts defined",
                              f"All {len(required_signals)} canonical alert signals are defined"))

    alerts_with_runbooks = [a for a in alerts if a.runbook]
    if len(alerts_with_runbooks) < len(alerts):
        findings.append(_warn(CAT_MON, "Runbook linked to every alert definition",
                              f"{len(alerts) - len(alerts_with_runbooks)} alert(s) have no runbook link",
                              "Add a runbook path to every alert — on-call engineers must be able to act in < 5 min"))
    else:
        findings.append(_pass(CAT_MON, "Runbook linked to every alert definition",
                              f"All {len(alerts)} alert(s) have linked runbooks"))

    phys_sites = [s for s in sites if s.ospf_area is not None]
    low_oncall = [s for s in phys_sites if s.on_call_contacts < 2]
    if low_oncall:
        findings.append(_warn(CAT_MON, "On-call rotation has >= 2 contacts at every site",
                              f"Only 1 contact at: {[s.name for s in low_oncall]} "
                              f"— solo on-call is a single point of failure",
                              "Add a secondary on-call contact at each under-staffed site"))
    else:
        findings.append(_pass(CAT_MON, "On-call rotation has >= 2 contacts at every site",
                              f"All {len(phys_sites)} physical site(s) have >= 2 on-call contacts"))

    wan_link_count = len([w for w in WAN_LINKS if w.bfd])
    if wan_link_count == 0:
        findings.append(_fail(CAT_MON, "BFD enabled on all WAN links for fast failure detection",
                              "No WAN links have BFD — failure detection relies on BGP/OSPF hold-down timers only",
                              "Enable BFD with 300 ms interval on all WAN-facing interfaces"))
    elif wan_link_count < len(WAN_LINKS):
        findings.append(_warn(CAT_MON, "BFD enabled on all WAN links for fast failure detection",
                              f"BFD missing on {len(WAN_LINKS) - wan_link_count} WAN link(s)",
                              "Enable BFD on remaining WAN links — 300 ms × 3 = 900 ms detection vs 30 s OSPF dead"))
    else:
        findings.append(_pass(CAT_MON, "BFD enabled on all WAN links for fast failure detection",
                              f"BFD active on all {len(WAN_LINKS)} WAN link(s)"))

    cloud_site = next((s for s in sites if "Cloud" in s.name), None)
    if cloud_site and not cloud_site.snmpv3:
        findings.append(_warn(CAT_MON, "Cloud VPC monitoring integrated with on-premises NOC",
                              "Cloud VPC SNMPv3 not confirmed — cloud health is a blind spot",
                              "Export CloudWatch metrics to the on-premises Prometheus via remote_write"))
    else:
        findings.append(_pass(CAT_MON, "Cloud VPC monitoring integrated with on-premises NOC",
                              "Cloud VPC has SNMPv3 and syslog forwarding to on-prem collector"))

    return findings


def score_findings(findings: list[Finding]) -> dict:
    categories: dict[str, dict] = {}
    for f in findings:
        if f.category not in categories:
            categories[f.category] = {"pass": 0, "warn": 0, "fail": 0, "score": 0, "max": 0}
        categories[f.category]["max"] += 10
        categories[f.category]["score"] += f.score
        categories[f.category][f.status.lower()] += 1
    total_score = sum(f.score for f in findings)
    total_max = len(findings) * 10
    pct = (total_score / total_max * 100) if total_max else 0
    if pct >= 90:
        grade = "PRODUCTION"
    elif pct >= 70:
        grade = "INTERNAL-ONLY"
    else:
        grade = "NOT-DEPLOYABLE"
    return {
        "total_score": total_score,
        "total_max": total_max,
        "pct": round(pct, 1),
        "grade": grade,
        "categories": categories,
    }


def print_report(findings: list[Finding], summary: dict) -> None:
    width = 78
    print("=" * width)
    print("Capstone Network Readiness Review — Meridian Technologies")
    print("Multi-Site Integrated Design: HQ + Branch-A + Branch-B + Cloud VPC")
    print("=" * width)

    print("\nSITE INVENTORY")
    for s in SITES:
        asn_str = f"AS {s.asn}" if s.asn else "transit"
        area_str = f"OSPF Area {s.ospf_area}" if s.ospf_area else "cloud-routed"
        print(f"  {s.name:<30}  {asn_str:<12}  {area_str:<16}  {s.block}")

    print("\nCATEGORY SCORES")
    cat_order = [CAT_ADDR, CAT_ROUT, CAT_SEC, CAT_QOS, CAT_MON]
    for cat in cat_order:
        c = summary["categories"].get(cat, {})
        score = c.get("score", 0)
        max_s = c.get("max", 0)
        pct = score / max_s * 100 if max_s else 0
        indicator = "PASS" if pct >= 90 else ("WARN" if pct >= 70 else "FAIL")
        print(f"  {cat:<40}  {score:>3}/{max_s:<3}  {pct:>5.1f}%  {indicator}")

    grade = summary["grade"]
    pct = summary["pct"]
    total = summary["total_score"]
    total_max = summary["total_max"]
    print(f"\nTOTAL SCORE: {total}/{total_max}  ({pct}%)  GRADE: {grade}")
    print()

    status_order = ["FAIL", "WARN", "PASS"]
    for status in status_order:
        group = [f for f in findings if f.status == status]
        if not group:
            continue
        label = {"FAIL": "FAIL", "WARN": "WARN", "PASS": "PASS"}[status]
        print(f"  --- {label} findings ({len(group)}) ---")
        for f in group:
            print(f"  [{f.status:<4}] {f.category:<32}  {f.check}")
            print(f"         {f.detail}")
        print()

    fail_items = [f for f in findings if f.status == "FAIL"]
    warn_items = [f for f in findings if f.status == "WARN"]

    if fail_items:
        print("REMEDIATION — Priority 1 (FAIL — fix within 1 week):")
        for i, f in enumerate(fail_items, 1):
            print(f"  {i}. [{f.category}] {f.check}")
            print(f"     Fix: {f.remediation}")
        print()

    if warn_items:
        print("REMEDIATION — Priority 2 (WARN — fix within 30 days):")
        for i, f in enumerate(warn_items, 1):
            print(f"  {i}. [{f.category}] {f.check}")
            print(f"     Fix: {f.remediation}")
        print()

    print("-" * width)
    report = {
        "design": "Meridian Technologies multi-site network — target state",
        "sites": [s.name for s in SITES],
        "total_score": summary["total_score"],
        "total_max": summary["total_max"],
        "score_pct": summary["pct"],
        "grade": summary["grade"],
        "findings": [
            {"category": f.category, "check": f.check, "status": f.status,
             "score": f.score, "detail": f.detail, "remediation": f.remediation}
            for f in findings
        ],
        "remediation_priority_1": [f.check for f in fail_items],
        "remediation_priority_2": [f.check for f in warn_items],
    }
    print(json.dumps(report, indent=2))


def main() -> None:
    findings: list[Finding] = []
    findings.extend(check_addressing(VLANS, WAN_LINKS, SITES))
    findings.extend(check_routing(OSPF_AREAS, BGP_SESSIONS))
    findings.extend(check_redundancy(VRRP_PAIRS, VLANS, WAN_LINKS))
    findings.extend(check_security(VLANS))
    findings.extend(check_qos(VLANS, QOS_CLASSES, WAN_LINKS))
    findings.extend(check_monitoring(SITES, ALERTS))
    summary = score_findings(findings)
    print_report(findings, summary)


if __name__ == "__main__":
    main()
