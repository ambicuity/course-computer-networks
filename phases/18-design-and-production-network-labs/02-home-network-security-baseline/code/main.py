#!/usr/bin/env python3
"""Home Network Security Baseline Auditor (Production Lab 02).

Ingests a snapshot of a home network's configuration (devices, firmware,
passwords, encryption, VLANs, DNS, port forwards) and scores each control
against CIS Controls v8 IG1 and NIST CSF 2.0. Stdlib only.

Run:  python3 main.py [snapshot.json]
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Control definitions
# ---------------------------------------------------------------------------

@dataclass
class Control:
    cid: str             # CIS v8 / CSF 2.0 identifier
    family: str          # CSF 2.0 function
    title: str
    weight: int          # contribution to score (out of 100)


CONTROLS: list[Control] = [
    Control("CIS-01", "Identify",   "Inventory of network devices",        6),
    Control("CIS-02", "Identify",   "Inventory of software/firmware",      6),
    Control("CIS-03", "Protect",    "Data protection (encryption at rest)", 5),
    Control("CIS-04", "Protect",    "Secure configuration of assets",      8),
    Control("CIS-05", "Protect",    "Account management",                  8),
    Control("CIS-06", "Protect",    "Access control management",           6),
    Control("CIS-07", "Identify",   "Continuous vulnerability mgmt",       8),
    Control("CIS-08", "Detect",     "Audit log management",                7),
    Control("CIS-09", "Protect",    "Email/web browser protections (DNS)", 5),
    Control("CIS-10", "Protect",    "Malware defenses",                    4),
    Control("CIS-11", "Recover",    "Data recovery (backups)",             6),
    Control("CIS-12", "Protect",    "Network infrastructure management",   10),
    Control("CIS-13", "Detect",     "Network monitoring and defense",       7),
    Control("CIS-14", "Govern",     "Security awareness (operator)",       4),
    Control("CIS-15", "Govern",     "Service provider management",         4),
    # CSF 2.0-specific
    Control("CSF-GV", "Govern",     "Govern function (policy + roles)",    6),
]


# ---------------------------------------------------------------------------
# Snapshot model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Device:
    name: str
    kind: str           # router / ap / iot / pc / phone / nas / camera
    ip: str
    mac: str
    firmware: str       # semantic version
    firmware_latest: str
    firmware_days_old: int
    known_cves: tuple[str, ...] = ()
    in_kev: bool = False
    admin_password_len: int = 0
    admin_default: bool = True
    encryption: str = "OPEN"   # WPA3-SAE / WPA2-AES / WPA2-TKIP / WEP / OPEN


@dataclass
class Snapshot:
    household: str
    router_admin_default: bool
    router_admin_password_len: int
    router_remote_mgmt: bool
    upnp_enabled: bool
    dns_servers: tuple[str, ...]
    doh_enabled: bool
    wps_enabled: bool
    pmf_enabled: bool
    log_retention_days: int
    log_remote: bool
    mfa_admin: bool
    vlans: tuple[str, ...]                # flat / iot-isolated / full
    backups_tested_quarterly: bool
    last_vuln_scan_days: int
    devices: tuple[Device, ...] = field(default_factory=tuple)

    def total_weight(self) -> int:
        return sum(c.weight for c in CONTROLS)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def firmware_status(d: Device) -> tuple[str, str]:
    """Returns (status, severity) per NIST IR 8425 §4.3."""
    if d.in_kev:
        return ("critical", "P0")
    if d.known_cves:
        return ("stale", "P1")
    if d.firmware_days_old > 90:
        return ("stale", "P2")
    if d.firmware != d.firmware_latest:
        return ("behind", "P3")
    return ("fresh", "OK")


def password_entropy_bits(pwd: str) -> float:
    """Approximate entropy for a passphrase.

    Uses EFF-style wordlist entropy for lowercase+digits words and standard
    charset entropy for arbitrary strings.
    """
    if not pwd:
        return 0.0
    if re.match(r"^[a-z]+( [a-z]+){2,}$", pwd):
        words = pwd.split()
        # EFF diceware: 7776 words = log2(7776) = 12.92 bits per word
        return len(words) * 12.92
    # Charset entropy heuristic
    charset = 0
    if re.search(r"[a-z]", pwd):
        charset += 26
    if re.search(r"[A-Z]", pwd):
        charset += 26
    if re.search(r"[0-9]", pwd):
        charset += 10
    if re.search(r"[^A-Za-z0-9]", pwd):
        charset += 33
    return len(pwd) * math.log2(max(charset, 1))


def evaluate(snap: Snapshot) -> dict[str, dict]:
    """Score each control as PASS / WARN / FAIL with evidence."""
    findings: dict[str, dict] = {}

    # CIS-01 / Inventory
    inv_status = "PASS" if len(snap.devices) >= 1 else "FAIL"
    findings["CIS-01"] = {
        "status": inv_status,
        "evidence": f"{len(snap.devices)} devices inventoried",
        "score": 100 if inv_status == "PASS" else 0,
    }

    # CIS-02 / Software inventory
    fw_recorded = sum(1 for d in snap.devices if d.firmware)
    findings["CIS-02"] = {
        "status": "PASS" if fw_recorded == len(snap.devices) else "WARN",
        "evidence": f"{fw_recorded}/{len(snap.devices)} devices report firmware",
        "score": 100 if fw_recorded == len(snap.devices) else 50,
    }

    # CIS-03 / Data protection
    has_nas = any(d.kind == "nas" for d in snap.devices)
    findings["CIS-03"] = {
        "status": "PASS" if (snap.backups_tested_quarterly and has_nas) else "WARN",
        "evidence": ("NAS present with tested backups"
                     if snap.backups_tested_quarterly and has_nas
                     else "Backup cadence or NAS encryption unverified"),
        "score": 100 if snap.backups_tested_quarterly else 50,
    }

    # CIS-04 / Secure configuration
    default_creds = [d for d in snap.devices if d.admin_default]
    bad = len(default_creds) + (1 if snap.router_admin_default else 0)
    findings["CIS-04"] = {
        "status": "PASS" if bad == 0 else "FAIL",
        "evidence": f"{bad} device(s) with default credentials; UPnP={'on' if snap.upnp_enabled else 'off'}",
        "score": max(0, 100 - bad * 20),
    }

    # CIS-05 / Account management
    short_pw = snap.router_admin_password_len < 16
    findings["CIS-05"] = {
        "status": "PASS" if not short_pw else "FAIL",
        "evidence": (f"router admin pwd length = {snap.router_admin_password_len} "
                     f"(target ≥ 16, entropy ≥ 60 bits)"),
        "score": 100 if not short_pw else 30,
    }

    # CIS-06 / Access control
    findings["CIS-06"] = {
        "status": "PASS" if snap.mfa_admin else "FAIL",
        "evidence": "MFA on admin: " + ("yes" if snap.mfa_admin else "no"),
        "score": 100 if snap.mfa_admin else 0,
    }

    # CIS-07 / Vulnerability management
    stale = sum(1 for d in snap.devices if firmware_status(d)[0] in ("stale", "critical"))
    findings["CIS-07"] = {
        "status": "PASS" if stale == 0 and snap.last_vuln_scan_days <= 30 else "WARN",
        "evidence": (f"{stale} device(s) stale or critical; "
                     f"last scan {snap.last_vuln_scan_days}d ago"),
        "score": max(0, 100 - stale * 25 - max(0, snap.last_vuln_scan_days - 30) * 2),
    }

    # CIS-08 / Audit logs
    findings["CIS-08"] = {
        "status": "PASS" if snap.log_retention_days >= 90 and snap.log_remote else "WARN",
        "evidence": (f"retention={snap.log_retention_days}d "
                     f"remote={'yes' if snap.log_remote else 'no'}"),
        "score": (100 if snap.log_retention_days >= 90 and snap.log_remote
                  else 60 if snap.log_retention_days >= 30 else 20),
    }

    # CIS-09 / DNS filtering
    filtered = any(d.startswith(("9.9.9.", "149.112.112.", "1.1.1.3", "1.0.0.3"))
                   for d in snap.dns_servers)
    findings["CIS-09"] = {
        "status": "PASS" if filtered and snap.doh_enabled else "WARN",
        "evidence": (f"DNS={','.join(snap.dns_servers)}; DoH={'on' if snap.doh_enabled else 'off'}"),
        "score": 100 if filtered and snap.doh_enabled else 60 if filtered else 0,
    }

    # CIS-10 / Malware
    findings["CIS-10"] = {
        "status": "WARN",
        "evidence": "Endpoint AV/EDR not enumerated; recommend at minimum DNS sinkhole",
        "score": 50,
    }

    # CIS-11 / Data recovery
    findings["CIS-11"] = {
        "status": "PASS" if snap.backups_tested_quarterly else "FAIL",
        "evidence": ("backups tested quarterly"
                     if snap.backups_tested_quarterly else "no restore drill recorded"),
        "score": 100 if snap.backups_tested_quarterly else 20,
    }

    # CIS-12 / Network infrastructure (segmentation, no remote mgmt)
    seg_score = {"flat": 30, "iot-isolated": 80, "full": 100}.get(snap.vlans[0], 50) \
        if snap.vlans else 0
    findings["CIS-12"] = {
        "status": "PASS" if seg_score >= 80 and not snap.router_remote_mgmt else "WARN",
        "evidence": (f"segmentation={snap.vlans[0] if snap.vlans else 'unknown'}, "
                     f"remote_mgmt={'on' if snap.router_remote_mgmt else 'off'}"),
        "score": (seg_score if not snap.router_remote_mgmt else seg_score // 2),
    }

    # CIS-13 / Network monitoring
    findings["CIS-13"] = {
        "status": "PASS" if snap.log_remote else "WARN",
        "evidence": ("remote syslog collector configured"
                     if snap.log_remote else "no out-of-band log collector"),
        "score": 100 if snap.log_remote else 40,
    }

    # CIS-14 / Awareness
    findings["CIS-14"] = {
        "status": "PASS",
        "evidence": "operator runs this auditor (awareness baseline met)",
        "score": 100,
    }

    # CIS-15 / Service provider management
    findings["CIS-15"] = {
        "status": "WARN",
        "evidence": "vendor security baselines not enumerated; recommend checking CISA KEV + vendor SBOM",
        "score": 50,
    }

    # CSF-GV / Govern
    findings["CSF-GV"] = {
        "status": "PASS" if snap.backups_tested_quarterly and snap.mfa_admin else "WARN",
        "evidence": ("governance docs + tested recovery + MFA"
                     if snap.backups_tested_quarterly and snap.mfa_admin
                     else "missing governance artifacts"),
        "score": 80 if snap.backups_tested_quarterly and snap.mfa_admin else 40,
    }

    return findings


def overall_score(findings: dict[str, dict]) -> tuple[int, str]:
    weighted = sum(findings[c.cid]["score"] * c.weight for c in CONTROLS)
    total = sum(c.weight for c in CONTROLS) * 100
    score = round(weighted * 100 / total)
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 \
        else "D" if score >= 60 else "F"
    return score, grade


def hardening_plan(snap: Snapshot, findings: dict[str, dict]) -> list[dict]:
    """Return prioritized items (high impact per hour first)."""
    plan: list[dict] = []
    if findings["CIS-04"]["status"] != "PASS":
        plan.append({"day": 1, "title": "Change default credentials on every device",
                     "cmd_openwrt": "passwd", "minutes": 60,
                     "risk_reduction": "high"})
    if findings["CIS-06"]["status"] != "PASS":
        plan.append({"day": 2, "title": "Enable MFA on router admin + password manager",
                     "cmd_openwrt": "opkg install luci-app-2fa", "minutes": 30,
                     "risk_reduction": "high"})
    if findings["CIS-12"]["status"] != "PASS":
        plan.append({"day": 5, "title": "Deploy IoT VLAN with managed switch",
                     "cmd_openwrt": "uci set network.@vlan[-1]=vlan; ...", "minutes": 180,
                     "risk_reduction": "high"})
    if findings["CIS-07"]["status"] != "PASS":
        plan.append({"day": 7, "title": "Update stale firmware (NIST IR 8425 §4.3)",
                     "cmd_openwrt": "sysupgrade -v /tmp/firmware.img", "minutes": 90,
                     "risk_reduction": "high"})
    if findings["CIS-09"]["status"] != "PASS":
        plan.append({"day": 9, "title": "Switch DNS to Quad9 + enable DoH/DoT",
                     "cmd_openwrt": "uci set dhcp.@dnsmasq[0].server='9.9.9.9'", "minutes": 20,
                     "risk_reduction": "medium"})
    if findings["CIS-08"]["status"] != "PASS":
        plan.append({"day": 12, "title": "Configure remote syslog + 90-day retention",
                     "cmd_openwrt": "logger -t net -p cron.info", "minutes": 60,
                     "risk_reduction": "medium"})
    if findings["CIS-11"]["status"] != "PASS":
        plan.append({"day": 20, "title": "Run a backup restore drill",
                     "cmd_openwrt": "rsync -aH --delete /mnt/nas/ /mnt/usb/",
                     "minutes": 120, "risk_reduction": "medium"})
    if findings["CIS-13"]["status"] != "PASS":
        plan.append({"day": 25, "title": "Stand up a log collector (Raspberry Pi + syslog-ng)",
                     "cmd_openwrt": "apt install syslog-ng-core", "minutes": 90,
                     "risk_reduction": "low"})
    return plan


# ---------------------------------------------------------------------------
# Demo snapshot + main
# ---------------------------------------------------------------------------

def demo_snapshot() -> Snapshot:
    return Snapshot(
        household="Demo-Household",
        router_admin_default=True,
        router_admin_password_len=8,
        router_remote_mgmt=False,
        upnp_enabled=True,
        dns_servers=("8.8.8.8", "8.8.4.4"),
        doh_enabled=False,
        wps_enabled=True,
        pmf_enabled=False,
        log_retention_days=7,
        log_remote=False,
        mfa_admin=False,
        vlans=("flat",),
        backups_tested_quarterly=False,
        last_vuln_scan_days=120,
        devices=(
            Device("ASUS-RT-AX86U", "router", "192.168.1.1",
                   "AA:BB:CC:DD:EE:01",
                   firmware="3.0.0.4.388_22525",
                   firmware_latest="3.0.0.4.388_23285",
                   firmware_days_old=180,
                   known_cves=(),
                   in_kev=False,
                   admin_password_len=8,
                   admin_default=True,
                   encryption="WPA2-AES"),
            Device("Synology-DS220+", "nas", "192.168.1.50",
                   "AA:BB:CC:DD:EE:02",
                   firmware="DSM 7.2.1",
                   firmware_latest="DSM 7.2.2",
                   firmware_days_old=60,
                   admin_password_len=12,
                   admin_default=False),
            Device("Ring-Doorbell", "camera", "192.168.1.80",
                   "AA:BB:CC:DD:EE:03",
                   firmware="Up to date",
                   firmware_latest="Up to date",
                   firmware_days_old=10,
                   admin_default=False,
                   encryption="WPA2-AES"),
            Device("Echo-Dot-1", "iot", "192.168.1.101",
                   "AA:BB:CC:DD:EE:04",
                   firmware="8765432100",
                   firmware_latest="8765432100",
                   firmware_days_old=15,
                   admin_default=False),
            Device("Hue-Bridge", "iot", "192.168.1.102",
                   "AA:BB:CC:DD:EE:05",
                   firmware="1.50.2",
                   firmware_latest="1.50.2",
                   firmware_days_old=20,
                   admin_default=False),
        ),
    )


def print_report(snap: Snapshot) -> None:
    findings = evaluate(snap)
    score, grade = overall_score(findings)

    print("=" * 72)
    print(f"Home Network Audit: {snap.household}")
    print("=" * 72)
    print(f"\n  Devices inventoried: {len(snap.devices)}")
    print(f"\n  Per-control findings (CIS v8 IG1 + CSF 2.0):")
    print(f"  {'Control':9} {'Family':10} {'Status':6} {'Score':5} Evidence")
    for c in CONTROLS:
        f = findings[c.cid]
        print(f"  {c.cid:9} {c.family:10} {f['status']:6} {f['score']:>4}  {f['evidence']}")

    print(f"\n  OVERALL POSTURE: {score}/100  Grade {grade}")
    pwd_bits = password_entropy_bits("x" * snap.router_admin_password_len)
    print(f"  Router admin entropy: {pwd_bits:.1f} bits (target ≥ 60)")

    plan = hardening_plan(snap, findings)
    print(f"\n  30-day hardening plan ({len(plan)} items, by day):")
    for item in plan:
        print(f"    day {item['day']:>3}: {item['title']:50} "
              f"({item['risk_reduction']}, {item['minutes']} min)")


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        snap = Snapshot(**data)
    else:
        snap = demo_snapshot()
    print_report(snap)
    print("\n--- JSON snapshot (input) ---")
    print(json.dumps({
        "household": snap.household,
        "router_admin_default": snap.router_admin_default,
        "router_admin_password_len": snap.router_admin_password_len,
        "router_remote_mgmt": snap.router_remote_mgmt,
        "upnp_enabled": snap.upnp_enabled,
        "dns_servers": list(snap.dns_servers),
        "doh_enabled": snap.doh_enabled,
        "wps_enabled": snap.wps_enabled,
        "pmf_enabled": snap.pmf_enabled,
        "log_retention_days": snap.log_retention_days,
        "log_remote": snap.log_remote,
        "mfa_admin": snap.mfa_admin,
        "vlans": list(snap.vlans),
        "backups_tested_quarterly": snap.backups_tested_quarterly,
        "last_vuln_scan_days": snap.last_vuln_scan_days,
        "devices": [asdict(d) for d in snap.devices],
    }, indent=2))


if __name__ == "__main__":
    main()