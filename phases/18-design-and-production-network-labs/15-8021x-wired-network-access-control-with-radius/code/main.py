"""802.1X wired NAC with RADIUS and EAP-TLS simulator.

Models a FreeRADIUS 3.2 instance talking to a Catalyst 9300 authenticator
and a Windows 11 / macOS / Linux supplicant. Replays three sessions:
a clean EAP-TLS, a TLS alert 42 (bad cert), and a MAB fallback. Stdlib-only,
type-annotated, prints a NAC design report. Does NOT touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PortState(str, Enum):
    UNAUTH = "UNAUTH"
    AUTH = "AUTH"
    AUTH_FAIL = "AUTH_FAIL"
    AUTH_MAB = "AUTH_MAB"
    HELD = "HELD"
    QUIET = "QUIET"


@dataclass(frozen=True)
class X509:
    """Minimal X.509-like cert for the simulator. Not a real cert."""
    subject_cn: str
    issuer_cn: str
    serial: int
    not_before: int   # unix epoch
    not_after: int
    revoked: bool = False
    san: tuple[str, ...] = ()

    def is_valid(self, now: int) -> tuple[bool, str]:
        if self.revoked:
            return False, "REVOKED"
        if now < self.not_before:
            return False, "NOT_YET_VALID"
        if now > self.not_after:
            return False, "EXPIRED"
        return True, "OK"


@dataclass(frozen=True)
class Supplicant:
    name: str
    mac: str
    cert: X509
    user: str
    realm: str = "research.lab"


@dataclass
class RadiusAttributes:
    tunnel_type: int = 0
    tunnel_medium: int = 0
    tunnel_private_group_id: str = ""
    session_timeout: int = 0
    filter_id: str = ""


@dataclass
class Session:
    supplicant: Supplicant
    state: PortState = PortState.UNAUTH
    radius_attrs: RadiusAttributes = field(default_factory=RadiusAttributes)
    reason: str = ""
    acct_session_id: str = ""
    eap_method: str = ""


class CertChain:
    """Tiny built-in CA chain. Root signs the issuing CA, which signs clients."""

    def __init__(self, now: int) -> None:
        self.now = now
        self.root = X509(
            subject_cn="Research Lab Root CA", issuer_cn="Research Lab Root CA",
            serial=1, not_before=now - 86400 * 365 * 5, not_after=now + 86400 * 365 * 2,
        )
        self.issuing = X509(
            subject_cn="Research Lab Issuing CA", issuer_cn="Research Lab Root CA",
            serial=2, not_before=now - 86400 * 365 * 3, not_after=now + 86400 * 365 * 1,
        )

    def validate(self, cert: X509) -> tuple[bool, str]:
        if cert.issuer_cn != self.issuing.subject_cn:
            return False, "UNKNOWN_ISSUER"
        valid, reason = cert.is_valid(self.now)
        if not valid:
            return False, reason
        return True, "OK"


@dataclass
class RadiusServer:
    chain: CertChain
    mab_allowlist: tuple[str, ...] = ()
    sessions: dict[str, Session] = field(default_factory=dict)

    def _acct_id(self, name: str) -> str:
        return f"acct-{abs(hash(name)) & 0xFFFF:04x}"

    def authenticate_eap_tls(self, sup: Supplicant) -> Session:
        sess = Session(sup=sup, eap_method="EAP-TLS")
        sess.acct_session_id = self._acct_id(sup.name)
        ok, reason = self.chain.validate(sup.cert)
        if not ok:
            sess.state = PortState.AUTH_FAIL
            sess.reason = f"TLS alert 42: {reason}"
            return sess
        sess.state = PortState.AUTH
        sess.radius_attrs = RadiusAttributes(
            tunnel_type=13, tunnel_medium=6, tunnel_private_group_id="200",
            session_timeout=28800, filter_id="permit tcp any host 10.40.0.0/16",
        )
        self.sessions[sess.acct_session_id] = sess
        return sess

    def authenticate_mab(self, sup: Supplicant) -> Session:
        sess = Session(sup=sup, eap_method="MAB")
        sess.acct_session_id = self._acct_id(sup.name + "-mab")
        oui = sup.mac[:8].lower()
        if oui in self.mab_allowlist:
            sess.state = PortState.AUTH_MAB
            sess.radius_attrs = RadiusAttributes(
                tunnel_type=13, tunnel_medium=6, tunnel_private_group_id="300",
                session_timeout=0, filter_id="permit tcp any host 10.40.0.0/16",
            )
        else:
            sess.state = PortState.AUTH_FAIL
            sess.reason = "MAB OUI not in allowlist"
        self.sessions[sess.acct_session_id] = sess
        return sess

    def change_of_authorization(self, acct_id: str, new_vlan: str) -> tuple[bool, str]:
        sess = self.sessions.get(acct_id)
        if sess is None:
            return False, "CoA-NAK: unknown session"
        sess.radius_attrs.tunnel_private_group_id = new_vlan
        return True, f"CoA-ACK: session {acct_id} -> VLAN {new_vlan}"


def build_supplicants(now: int) -> list[Supplicant]:
    return [
        Supplicant(
            name="cfo-laptop", mac="aa:bb:cc:00:00:05",
            cert=X509("cfo-laptop.research.lab", "Research Lab Issuing CA",
                      100, now - 86400 * 90, now + 86400 * 365, san=("cfo-laptop.research.lab",)),
            user="alice", realm="research.lab",
        ),
        Supplicant(
            name="contractor-mac-RETIRED", mac="aa:bb:cc:de:ad:be",
            cert=X509("contractor-mac.research.lab", "Research Lab Issuing CA",
                      101, now - 86400 * 800, now - 86400 * 100, revoked=True),
            user="bob", realm="research.lab",
        ),
        Supplicant(
            name="floor-printer-01", mac="00:1b:a9:00:11:22",
            cert=X509("floor-printer-01", "Research Lab Issuing CA",
                      200, now - 86400 * 200, now + 86400 * 165),
            user="floor-printer-01", realm="mab",
        ),
    ]


def run_audit(server: RadiusServer, sups: list[Supplicant]) -> list[Session]:
    results: list[Session] = []
    s1 = server.authenticate_eap_tls(sups[0])
    results.append(s1)
    s2 = server.authenticate_eap_tls(sups[1])
    results.append(s2)
    s3 = server.authenticate_mab(sups[2])
    results.append(s3)
    return results


def print_report(results: list[Session]) -> None:
    bar = "=" * 64
    print(bar)
    print(" 802.1X / RADIUS / EAP-TLS NAC Design Report ")
    print(" Reference: FreeRADIUS 3.2, Catalyst 9300, EAP-TLS + MAB ")
    print(bar)
    for s in results:
        a = s.radius_attrs
        print(f"  Supplicant : {s.supplicant.name}")
        print(f"  Method     : {s.eap_method}")
        print(f"  Acct-SessId: {s.acct_session_id}")
        print(f"  Port state : {s.state.value}")
        if s.reason:
            print(f"  Reason     : {s.reason}")
        if a.tunnel_private_group_id:
            print(f"  Tunnel     : Type={a.tunnel_type} Medium={a.tunnel_medium} "
                  f"VLAN={a.tunnel_private_group_id}")
            print(f"  Filter-Id  : {a.filter_id}")
        print("-" * 64)


def main() -> None:
    now = 1_700_000_000
    chain = CertChain(now=now)
    server = RadiusServer(chain=chain, mab_allowlist=("00:1b:a9", "00:1c:c4"))
    sups = build_supplicants(now)
    results = run_audit(server, sups)
    print_report(results)
    print(" CoA bounce: pushing cfo-laptop to VLAN 888 (remediation) ...")
    s1 = results[0]
    ok, msg = server.change_of_authorization(s1.acct_session_id, "888")
    print(f"  -> {msg}")
    print(" Final state of cfo-laptop: VLAN",
          s1.radius_attrs.tunnel_private_group_id)
    print("=" * 64)


if __name__ == "__main__":
    main()
