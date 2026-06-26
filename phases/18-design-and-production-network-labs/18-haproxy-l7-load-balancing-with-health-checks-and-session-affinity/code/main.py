#!/usr/bin/env python3
"""HAProxy L7 Load Balancer Planner (Production Lab 18).

Generates a complete haproxy.cfg with active health checks, session
affinity, TLS termination, and a stats page. Stdlib only.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from ipaddress import IPv4Address
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class Server:
    name: str
    ip: str
    port: int
    weight: int = 100
    maxconn: int = 5000


@dataclass
class Backend:
    name: str
    algorithm: str          # roundrobin / leastconn / source
    servers: list[Server]
    healthcheck_uri: str = "/healthz"
    healthcheck_status: int = 200
    inter_ms: int = 2000
    rise: int = 3
    fall: int = 3
    stick_type: str = "ip"  # ip / cookie / none
    stick_cookie: str = "SRV"
    stick_expire_s: int = 1800


@dataclass
class Frontend:
    name: str
    bind_port: int
    ssl_cert: str = ""
    ssl_min_ver: str = "TLSv1.2"
    acls: list[tuple[str, str, str]] = field(default_factory=list)  # (name, path_beg, backend)


# ---------------------------------------------------------------------------
# haproxy.cfg generator
# ---------------------------------------------------------------------------

def gen_global() -> str:
    return """global
    daemon
    maxconn 100000
    log /dev/log local0
    log /dev/log local1 notice
    chroot /var/lib/haproxy
    stats socket /var/run/haproxy.sock mode 600 level admin
    stats timeout 30s
    user haproxy
    group haproxy
    ssl-default-bind-ciphersuites TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256
    ssl-default-bind-options prefer-client-ciphers no-sslv3 no-tlsv10 no-tlsv11
"""


def gen_defaults() -> str:
    return """defaults
    log     global
    mode    http
    option  httplog
    option  dontlognull
    option  http-server-close
    timeout connect 5s
    timeout client  50s
    timeout server  50s
    timeout http-request 10s
    timeout queue   30s
"""


def gen_frontend(fe: Frontend) -> str:
    if fe.ssl_cert:
        bind = f"    bind *:{fe.bind_port} ssl crt {fe.ssl_cert} alpn h2,http/1.1"
    else:
        bind = f"    bind *:{fe.bind_port}"
    acls = "\n".join(
        f"    acl {n} path_beg {p}\n    use_backend {b} if {n}"
        for n, p, b in fe.acls
    )
    return f"""frontend {fe.name}
{bind}
    {f"ssl-min-ver {fe.ssl_min_ver}" if fe.ssl_cert else ""}
    {f"http-response set-header Strict-Transport-Security max-age=31536000\\; includeSubDomains\\; preload" if fe.ssl_cert else ""}
{acls}
    default_backend web
"""


def gen_backend(b: Backend) -> str:
    servers = "\n".join(
        f"    server {s.name} {s.ip}:{s.port} weight {s.weight} "
        f"maxconn {s.maxconn} check inter {b.inter_ms}ms rise {b.rise} fall {b.fall}"
        for s in b.servers
    )
    stick = ""
    if b.stick_type == "ip":
        stick = (
            f"    stick-table type ip size 100k expire {b.stick_expire_s}s\n"
            f"    stick on src"
        )
    elif b.stick_type == "cookie":
        stick = (
            f"    stick-table type string size 100k expire {b.stick_expire_s}s\n"
            f"    cookie {b.stick_cookie} insert indirect nocache\n"
            f"    stick on cookie({b.stick_cookie})"
        )
    healthcheck = (
        f"    option httpchk GET {b.healthcheck_uri} HTTP/1.1\\r\\nUser-Agent:\\ HAProxy-HealthCheck\\r\\n\\r\\n"
        f"    http-check expect status {b.healthcheck_status}"
    )
    return f"""backend {b.name}
    balance {b.algorithm}
{healthcheck}
{stick}
{servers}
"""


def gen_stats() -> str:
    return """listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 10s
    stats auth admin:secret
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api = Backend(
        name="api",
        algorithm="leastconn",
        servers=[
            Server("api-1", "10.0.1.10", 8080),
            Server("api-2", "10.0.1.11", 8080),
            Server("api-3", "10.0.1.12", 8080),
        ],
        stick_type="cookie",
        stick_cookie="JSESSIONID",
    )
    web = Backend(
        name="web",
        algorithm="roundrobin",
        servers=[
            Server("web-1", "10.0.2.10", 8000),
            Server("web-2", "10.0.2.11", 8000),
        ],
        stick_type="ip",
    )
    fe = Frontend(
        name="https",
        bind_port=443,
        ssl_cert="/etc/ssl/cert.pem",
        acls=[("url_api", "/api", "api"), ("url_static", "/static", "web")],
    )

    cfg = "\n".join([
        gen_global(), gen_defaults(),
        gen_frontend(fe),
        gen_backend(api),
        gen_backend(web),
        gen_stats(),
    ])
    with open("outputs/haproxy.cfg", "w") as f:
        f.write(cfg)
    print(f"Wrote outputs/haproxy.cfg ({len(cfg)} bytes)")

    # Verify with haproxy -c if available
    print()
    print("--- Verification matrix ---")
    matrix = [
        ("haproxy -c -f /etc/haproxy/haproxy.cfg", "config syntax check"),
        ("curl -vk https://localhost/healthz", "active health check (API)"),
        ("curl -vk --cookie 'JSESSIONID=abc' https://localhost/api/users",
         "session affinity via cookie"),
        ("curl -v https://localhost/", "default backend (web)"),
        ("echo 'show stat' | socat /var/run/haproxy.sock -", "stats via socket"),
        ("ss -tnp | grep :443", "TLS listener active"),
        ("haproxy -d -f /etc/haproxy/haproxy.cfg", "debug mode (foreground)"),
        ("openssl s_client -connect localhost:443 -tls1_3", "TLS 1.3 handshake"),
    ]
    for cmd, desc in matrix:
        print(f"  {desc:50s}  $ {cmd}")


if __name__ == "__main__":
    main()
