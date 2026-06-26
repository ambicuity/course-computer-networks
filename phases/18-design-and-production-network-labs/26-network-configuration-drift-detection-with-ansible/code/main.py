"""Configuration drift detection for network devices.

Stdlib-only: no paramiko, no netmiko, no napalm, no jsonpatch. Suitable for
execution on a hardened Ansible control node. The pipeline is:

  intent (Git) ─┐
                 ├─▶ Normalizer ─▶ SHA-256 (RFC 8785) ─▶ RFC 6902 patch
  observed ─────┘
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Canonicalization (RFC 8785 subset)
# ---------------------------------------------------------------------------

def canonical_dump(value: Any) -> str:
    """Return a deterministic byte-equal string for any JSON-serializable value.

    All object keys are sorted lexicographically. No insignificant whitespace
    is emitted. This matches the subset of RFC 8785 we need for fingerprinting.
    """
    if isinstance(value, dict):
        parts = ["{"]
        items = sorted(value.items(), key=lambda kv: kv[0])
        for i, (k, v) in enumerate(items):
            if i:
                parts.append(",")
            parts.append(json.dumps(k, ensure_ascii=False))
            parts.append(":")
            parts.append(canonical_dump(v))
        parts.append("}")
        return "".join(parts)
    if isinstance(value, list):
        return "[" + ",".join(canonical_dump(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def fingerprint(value: Any) -> str:
    """Return a hex-encoded SHA-256 fingerprint of the canonicalized value."""
    return hashlib.sha256(canonical_dump(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Normalizer registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedConfig:
    """The unified schema produced by the normalizer.

    Fields are deliberately frozen so downstream code cannot accidentally mutate
    the intent after fingerprinting.
    """
    bgp: dict[str, Any]
    ospf: dict[str, Any]
    ntp: dict[str, Any]
    vrf: list[dict[str, Any]]
    static_routes: list[dict[str, Any]]


def _scrub_timestamps(text: str) -> str:
    """Strip vendor timestamps that change on every show run."""
    banned = ("! Last configuration change", "## Last commit", "!! Last reload")
    return "\n".join(
        line for line in text.splitlines() if not any(line.startswith(b) for b in banned)
    )


def normalize_cisco(raw: str) -> NormalizedConfig:
    """Parse a synthetic Cisco IOS XE 17.9 running-config."""
    bgp: dict[str, Any] = {"asn": 0, "neighbors": []}
    ospf: dict[str, Any] = {"process_id": 0, "areas": []}
    ntp: dict[str, Any] = {"servers": [], "vrf": "global"}
    vrf: list[dict[str, Any]] = []
    static_routes: list[dict[str, Any]] = []
    current_vrf = "global"
    for line in _scrub_timestamps(raw).splitlines():
        s = line.strip()
        if s.startswith("router bgp "):
            bgp["asn"] = int(s.split()[2])
        elif s.startswith("neighbor ") and "remote-as" in s:
            parts = s.split()
            bgp["neighbors"].append({"ip": parts[1], "remote_as": int(parts[3])})
        elif s.startswith("router ospf "):
            ospf["process_id"] = int(s.split()[2])
        elif s.startswith("vrf definition "):
            current_vrf = s.split()[2]
            vrf.append({"name": current_vrf, "rd": None})
        elif s.startswith("ntp server "):
            ntp["servers"].append(s.split()[2])
        elif s.startswith("ip route "):
            parts = s.split()
            static_routes.append(
                {"prefix": parts[2], "mask": parts[3], "next_hop": parts[4], "vrf": current_vrf}
            )
    ntp["vrf"] = current_vrf if ntp["servers"] else "global"
    return NormalizedConfig(bgp=bgp, ospf=ospf, ntp=ntp, vrf=vrf, static_routes=static_routes)


NORMALIZERS: dict[str, Callable[[str], NormalizedConfig]] = {
    "cisco": normalize_cisco,
}


def normalize(vendor: str, raw: str) -> NormalizedConfig:
    if vendor not in NORMALIZERS:
        raise ValueError(f"unknown vendor: {vendor}")
    return NORMALIZERS[vendor](raw)


# ---------------------------------------------------------------------------
# Structural diff: produces an RFC 6902 JSON Patch
# ---------------------------------------------------------------------------

@dataclass
class DriftReport:
    intent_fp: str
    observed_fp: str
    drift_detected: bool
    patch: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


def _keyed_index(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return {item[key]: i for i, item in enumerate(items) if key in item}


def _key_for(path: str) -> str:
    """Return the dict key used to identify list elements for a given path."""
    return "ip" if path.endswith("/neighbors") else "prefix" if path.endswith("/static_routes") else ""


def diff(left: Any, right: Any, path: str = "") -> list[dict[str, Any]]:
    """Recursively diff two JSON-compatible values and emit JSON Patch ops."""
    ops: list[dict[str, Any]] = []
    if type(left) is not type(right):
        return [{"op": "replace", "path": path, "value": right}]
    if isinstance(left, dict):
        for k in sorted(set(left) | set(right)):
            p = f"{path}/{k}"
            if k not in left:
                ops.append({"op": "add", "path": p, "value": right[k]})
            elif k not in right:
                ops.append({"op": "remove", "path": p})
            else:
                ops.extend(diff(left[k], right[k], p))
        return ops
    if isinstance(left, list):
        key = _key_for(path)
        if key:
            lidx, ridx = _keyed_index(left, key), _keyed_index(right, key)
            for k in sorted(set(lidx) | set(ridx)):
                if k not in lidx:
                    ops.append({"op": "add", "path": f"{path}/{ridx[k]}", "value": right[ridx[k]]})
                elif k not in ridx:
                    ops.append({"op": "remove", "path": f"{path}/{lidx[k]}"})
                else:
                    ops.extend(diff(left[lidx[k]], right[ridx[k]], f"{path}/{lidx[k]}"))
            return ops
        for i in range(max(len(left), len(right))):
            p = f"{path}/{i}"
            if i >= len(left):
                ops.append({"op": "add", "path": p, "value": right[i]})
            elif i >= len(right):
                ops.append({"op": "remove", "path": p})
            else:
                ops.extend(diff(left[i], right[i], p))
        return ops
    if left != right:
        ops.append({"op": "replace", "path": path, "value": right})
    return ops


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def build_report(intent_path: Path, observed_path: Path, vendor: str) -> DriftReport:
    intent_raw = intent_path.read_text(encoding="utf-8")
    observed_raw = observed_path.read_text(encoding="utf-8")
    intent = normalize(vendor, intent_raw)
    observed = normalize(vendor, observed_raw)
    intent_dict = intent.__dict__
    observed_dict = observed.__dict__
    intent_fp = fingerprint(intent_dict)
    observed_fp = fingerprint(observed_dict)
    if intent_fp == observed_fp:
        return DriftReport(intent_fp, observed_fp, False, [], "no drift")
    patch = diff(intent_dict, observed_dict, "")
    return DriftReport(
        intent_fp=intent_fp,
        observed_fp=observed_fp,
        drift_detected=True,
        patch=patch,
        summary=f"{len(patch)} change(s) detected",
    )


def emit_junit(report: DriftReport, out: Path) -> None:
    if not report.drift_detected:
        body = '<testsuite name="drift" tests="1" failures="0"><testcase name="no-drift"/></testsuite>'
    else:
        body = (
            f'<testsuite name="drift" tests="1" failures="1">'
            f'<testcase name="drift-detected">'
            f'<failure message="drift detected" type="drift">'
            f'{json.dumps(report.patch)}'
            f'</failure></testcase></testsuite>'
        )
    out.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--observed", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("report.json"))
    parser.add_argument("--vendor", default="cisco", choices=sorted(NORMALIZERS))
    parser.add_argument("--format", default="json", choices=("json", "junit"))
    args = parser.parse_args()
    report = build_report(args.intent, args.observed, args.vendor)
    if args.format == "json":
        args.output.write_text(
            json.dumps(report.__dict__, indent=2, sort_keys=True), encoding="utf-8"
        )
    else:
        emit_junit(report, args.output)
    print(f"intent_fp   = {report.intent_fp}")
    print(f"observed_fp = {report.observed_fp}")
    print(f"drift       = {report.drift_detected}")
    print(f"summary     = {report.summary}")
    if report.drift_detected:
        print(f"patch ops   = {len(report.patch)}")
        for op in report.patch:
            print(f"  {op['op']:7s} {op['path']}")
    return 1 if report.drift_detected else 0


if __name__ == "__main__":
    sys.exit(main())
