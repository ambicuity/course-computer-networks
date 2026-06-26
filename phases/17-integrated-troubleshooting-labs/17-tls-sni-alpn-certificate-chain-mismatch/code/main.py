#!/usr/bin/env python3
"""TLS SNI/ALPN and certificate chain validation diagnostic.

Reference oracle for the integrated troubleshooting lab. Given a
synthetic ClientHello (SNI + ALPN offers) and a synthetic Certificate
record (leaf + chain), classifies the failure mode and prints the
verdict and corrective action.

Modes:

  hostname_mismatch
    Server returned a leaf whose subject/SAN does not contain the
    hostname the client requested. SNI was sent, server picked the
    default certificate by mistake.

  chain_incomplete
    Server returned only the leaf; the intermediate is missing.
    Client cannot bridge to a trusted root.

  alpn_refused
    Client offered ALPN 'h2' but the ServerHello did not select any
    ALPN, so the connection falls back to http/1.1.

  ok
    All three checks pass.

Run:  python3 main.py --mode hostname_mismatch
      python3 main.py --mode chain_incomplete
      python3 main.py --mode alpn_refused
      python3 main.py --mode ok
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClientHello:
    """The relevant fields of a ClientHello for the lab."""

    sni: str
    alpn_offers: tuple[str, ...]


@dataclass(frozen=True)
class CertEntry:
    subject: str
    issuer: str
    san: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Certificate:
    entries: tuple[CertEntry, ...]
    server_alpn: str | None


def hello() -> ClientHello:
    return ClientHello(sni="api.example.com", alpn_offers=("h2", "http/1.1"))


def leaf_for(name: str) -> CertEntry:
    return CertEntry(
        subject=f"CN = {name}",
        issuer="CN = DigiCert Global G2",
        san=(name, f"*.{name}"),
    )


def digi_intermediate() -> CertEntry:
    return CertEntry(subject="CN = DigiCert Global G2", issuer="CN = DigiCert Root CA")


def classify(client: ClientHello, server: Certificate) -> tuple[str, str, str]:
    if not server.entries:
        return ("chain_incomplete", "no certificate returned", "server")
    leaf = server.entries[0]
    if client.sni and client.sni not in leaf.san:
        return (
            "hostname_mismatch",
            f"requested SNI {client.sni!r} not in SAN list {leaf.san!r}",
            "server returned the wrong leaf",
        )
    if len(server.entries) < 2:
        return (
            "chain_incomplete",
            "server returned leaf only; intermediate is missing",
            "server should send full chain",
        )
    if "h2" in client.alpn_offers and server.server_alpn is None:
        return (
            "alpn_refused",
            f"client offered {client.alpn_offers!r} but server selected no ALPN",
            "client falls back to http/1.1; server lacks ALPN support for h2",
        )
    return ("ok", "SNI matches SAN, chain is complete, ALPN negotiated", "no action")


def render(client: ClientHello, server: Certificate, mode: str, reason: str, layer: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"TLS SNI/ALPN/CHAIN DIAGNOSTIC  --  verdict: {mode}")
    out.append("=" * 64)
    out.append("")
    out.append("ClientHello:")
    out.append(f"  SNI             : {client.sni}")
    out.append(f"  ALPN offers     : {list(client.alpn_offers)}")
    out.append("")
    out.append("Server Certificate record:")
    for i, c in enumerate(server.entries):
        out.append(f"  {i} subject       : {c.subject}")
        out.append(f"    issuer        : {c.issuer}")
        out.append(f"    SAN           : {list(c.san)}")
    out.append(f"  ServerHello ALPN: {server.server_alpn}")
    out.append("")
    out.append(f"Verdict : {mode.upper()}")
    out.append(f"Reason  : {reason}")
    out.append(f"Layer   : {layer}")
    if mode == "hostname_mismatch":
        out.append("Action  : check server's vhost config; the SNI the client sent is")
        out.append("          not mapped to a certificate on this server.")
    elif mode == "chain_incomplete":
        out.append("Action  : configure the server to send the full chain, not just the leaf.")
    elif mode == "alpn_refused":
        out.append("Action  : enable ALPN 'h2' on the server, or accept http/1.1 on the client.")
    else:
        out.append("Action  : no action; chain and ALPN are clean.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--mode",
        choices=("hostname_mismatch", "chain_incomplete", "alpn_refused", "ok"),
        default="hostname_mismatch",
    )
    args = parser.parse_args()

    client = hello()
    if args.mode == "hostname_mismatch":
        server = Certificate(entries=(leaf_for("app.example.com"), digi_intermediate()), server_alpn="h2")
    elif args.mode == "chain_incomplete":
        server = Certificate(entries=(leaf_for("api.example.com"),), server_alpn="h2")
    elif args.mode == "alpn_refused":
        server = Certificate(entries=(leaf_for("api.example.com"), digi_intermediate()), server_alpn=None)
    else:
        server = Certificate(entries=(leaf_for("api.example.com"), digi_intermediate()), server_alpn="h2")

    mode, reason, layer = classify(client, server)
    print(render(client, server, mode, reason, layer))


if __name__ == "__main__":
    main()
