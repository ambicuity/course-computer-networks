# HAProxy L7 Load Balancing with Active Health Checks and Session Affinity

> A modern web application is a multi-tier system: a TLS termination layer, an L7 reverse proxy (HAProxy, NGINX, Envoy), an application tier (Java, Go, Python, Node.js), a cache tier (Redis, Memcached), and a database tier (PostgreSQL, MySQL, MongoDB). The L7 reverse proxy is the single point that every external request passes through, and it is the single point that determines whether the user sees a fast, available service or a slow, broken one. A well-configured HAProxy can handle 100,000+ concurrent connections, sub-millisecond decision time per request, 99.999% availability, and a rich set of behaviors: **active health checks** (probe the backend with a synthetic request, not just a TCP connect), **passive health checks** (monitor the live traffic for failed responses), **session affinity** ("sticky sessions" — the same client always goes to the same backend, for stateful applications that store session data locally), **TLS termination** (with the right cipher suite list, the right OCSP stapling, and the right HSTS policy), **rate limiting and connection limits** (per-IP, per-backend, per-route), and **rich observability** (the HAProxy stats page, the Prometheus exporter, the structured logs). This lesson is the working playbook for HAProxy 2.8 in production: the `haproxy.cfg` structure, the `frontend` and `backend` sections, the `listen` shortcut, the `server` lines with their health-check and weight options, the `stick-table` for session affinity and rate limiting, the `log` directives and the structured-logging format, the stats and Prometheus integration, and the operational runbook (the cutover, the rollback, the failure modes). The deliverable is a Python HAProxy planner that takes a backend list, a health-check profile, a session-affinity policy, and a set of frontends, and outputs a complete `haproxy.cfg` plus a verification matrix.

**Type:** Build
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, enum), shell, HAProxy 2.8, curl
**Prerequisites:** Phase 12 HTTP, Phase 18 lesson 19 (TLS)
**Time:** ~130 minutes

## Learning Objectives

- Explain the **HAProxy architecture**: the `global` section (process-wide settings), the `defaults` section (per-section defaults), the `frontend` (the listening side), the `backend` (the pool of servers), and the `listen` (a frontend+backend shortcut).
- Configure **active health checks** (`httpchk`, `option httpchk`, `http-check send`, `http-check expect`) with the right interval, the right expected status code, and the right failure threshold.
- Configure **passive health checks** (`observe`, `error-limit`) and the **stick-table** for tracking per-server health, per-IP request count, and per-session persistence.
- Implement **session affinity** (`stick-table type ip size 100k expire 30m`, `stick on src`, `cookie <name> insert indirect nocache`) and choose the right method (source IP, cookie, header) for the application.
- Configure **TLS termination** (`bind *:443 ssl crt /etc/ssl/cert.pem`, `ssl-default-bind-ciphers`, `ssl-min-ver TLSv1.2`, `option ssl-hello-first`) with the right cipher list and the right HSTS policy.
- Build a **verification matrix** (curl -v, haproxy -c -f, haproxy -d, ss -tnp, haproxy stats) that proves the configuration is correct and the behavior is as designed.

## The Problem

A retail SaaS company, "ShopWave," operates a 4-tier web application serving 50,000 concurrent users at peak. The current NGINX setup is at its limit: 5,000 concurrent connections, 200 ms tail latency under load, frequent 502s during health-check failures, and no way to drain a backend for maintenance without a customer-visible outage. The senior engineer must replace NGINX with HAProxy 2.8, add active health checks, add session affinity, add the Prometheus exporter, and add a structured-logging pipeline. The deliverable is a single `haproxy.cfg` that handles the cutover without downtime.

The lesson's planner builds the configuration, the health-check profile, the session-affinity table, and the verification matrix.

## The Concept

### The haproxy.cfg structure and the global/defaults sections

The `haproxy.cfg` file has five sections: `global`, `defaults`, `frontend`, `backend`, and `listen`. The `global` section has process-wide settings: the daemon flag, the user/group, the log destinations, the maxconn, the SSL defaults, the thread count. The `defaults` section has per-section defaults: the log, the mode (http/tcp), the option set, the timeout values, the load-balancing algorithm.

The lesson's planner emits a `global` section with daemon mode, the HAProxy 2.8 chroot, the `log /dev/log local0` syslog destination, the `maxconn 100000`, and the SSL defaults; a `defaults` section with `log global`, `mode http`, `option httplog`, `option dontlognull`, `timeout connect 5s`, `timeout client 50s`, `timeout server 50s`, and the load-balancing algorithm (e.g., `roundrobin`, `leastconn`, `source`).

### The frontend and the backend

The **frontend** is the listening side. It binds to an IP:port, parses the incoming traffic, and routes it to a backend based on ACLs. The `bind` directive specifies the listener; the `acl` directives define the conditions; the `use_backend` directive routes to a backend.

The **backend** is the pool of servers. It defines the load-balancing algorithm, the server list, the health-check configuration, the stick-table, and the request/response options. The `server` directive specifies a single server with its IP:port, its weight, its maxconn, its health-check options.

The lesson's planner emits a frontend that binds to `*:80` and `*:443 ssl crt /etc/ssl/cert.pem`, with ACLs that route `/api` to the API backend, `/static` to the static-content backend, and `/` to the web backend; and three backends (API, static, web) each with the right server list and health-check.

### Active health checks and the httpchk family

**Active health checks** are probes that HAProxy sends to the backend on a regular interval, regardless of the live traffic. The probe is a configurable HTTP request (e.g., `GET /health HTTP/1.1`), and the expected response is a configurable status code or body. The backend is marked "up" if the probe succeeds, "down" if it fails. The active check has three advantages over the passive check: it can detect a backend that is not receiving traffic (e.g., a backend that all sessions are routed away from), it can detect a backend that is partially up (e.g., a backend that responds to the health check but returns 500s for the actual request), and it can be configured to send a specific request that exercises the application's logic (e.g., a database query).

The `option httpchk` directive enables the active check, the `http-check send` directive specifies the request, and the `http-check expect` directive specifies the expected response. The `inter` parameter sets the interval, the `rise` parameter sets the number of successes to mark the backend up, the `fall` parameter sets the number of failures to mark the backend down.

The lesson's planner emits the active-check configuration with `inter 2s`, `rise 3`, `fall 3`, and a synthetic request `GET /healthz HTTP/1.1\r\nUser-Agent: HAProxy-HealthCheck\r\n`.

### Session affinity and the stick-table

**Session affinity** (also called "sticky sessions" or "session persistence") is the property that the same client always goes to the same backend. It is required for stateful applications that store session data locally (e.g., a Java app that uses HttpSession, a PHP app that uses `$_SESSION`). Without session affinity, a user may be routed to a different backend on every request, and the session data is lost.

The stick-table is the data structure that HAProxy uses to track the session-affinity mapping. It can be keyed by source IP, by cookie, by header, or by any other request attribute. The `stick on src` directive enables source-IP affinity (the same source IP always goes to the same backend), the `stick-table type ip size 100k expire 30m` directive defines the stick-table, and the `cookie <name> insert indirect nocache` directive enables cookie-based affinity (the cookie is set by HAProxy and used to route subsequent requests).

The lesson's planner emits the stick-table and the affinity configuration, with the right type (ip / string / binary), the right size (number of entries), and the right expire time (how long the entry is kept).

### TLS termination and the cipher list

**TLS termination** at the HAProxy is the standard production pattern: the client connects with TLS, HAProxy terminates the TLS, and HAProxy connects to the backend with HTTP (or with TLS for re-encryption). The TLS termination has three sub-questions: the certificate (where it is stored, how it is loaded, how it is renewed), the cipher list (which ciphers are allowed, which are not), and the protocol version (TLS 1.2 minimum, TLS 1.3 preferred).

The lesson's planner emits the `bind *:443 ssl crt /etc/ssl/cert.pem` directive, the `ssl-default-bind-ciphersuites` (for TLS 1.3) and `ssl-default-bind-options` (for TLS 1.2), the `ssl-min-ver TLSv1.2` directive, and the `option ssl-hello-first` directive (to handle clients that send a TLS ClientHello before an HTTP request).

The cipher list is the most security-sensitive part. The lesson's planner uses a modern cipher list (e.g., ECDHE+AESGCM, ECDHE+CHACHA20) and excludes weak ciphers (RC4, 3DES, MD5-based MACs).

### The stats page and the Prometheus exporter

The **stats page** is HAProxy's built-in web interface that shows the live state of every frontend, backend, and server. It is enabled with the `stats enable` directive in a `listen` block, and it is protected with `stats auth <user>:<password>`. The stats page shows the current connection count, the request rate, the response time, the error rate, and the up/down state of every server.

The **Prometheus exporter** is a separate process that queries the HAProxy stats socket (over the Unix socket or the TCP socket) and exposes the metrics in the Prometheus format. The exporter is typically a small Go or Python program, and it is wired to Prometheus via a scrape job.

The lesson's planner emits the stats and Prometheus configuration, with the right path, the right auth, and the right metrics.

## Build It

The deliverable is `code/main.py`, a deterministic HAProxy planner. Inputs are: a list of frontends (port, ACLs, TLS cert path), a list of backends (algorithm, server list, health-check profile, session-affinity policy), and a global configuration (maxconn, log, SSL defaults). Outputs are: a complete `haproxy.cfg`, a health-check verification matrix, a session-affinity verification matrix, and a TLS verification matrix.

Run it: `python3 code/main.py`. The output is the `haproxy.cfg` and a verification matrix.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| `haproxy.cfg` | `haproxy -c -f` clean; global, defaults, frontend, backend sections | Pass |
| Active health check | `inter 2s`, `rise 3`, `fall 3`, expected 200 | Pass |
| Passive health check | `observe layer4`, `error-limit 50` | Pass |
| Session affinity | `stick-table type ip size 100k expire 30m`, `stick on src` | Pass |
| TLS termination | `bind *:443 ssl`, `ssl-min-ver TLSv1.2`, HSTS | Pass |
| Stats page | `stats enable`, `stats auth`, port 8404 | Pass |
| Prometheus exporter | `expose-fd listeners`, `/metrics` | Pass |
| Verification matrix | curl 200/404/500, haproxy -c, ss -tnp | Pass |

## Ship It

The artifact is `outputs/haproxy.cfg` plus a verification matrix. The output directory should also contain `prometheus_haproxy.yml` (the Prometheus scrape config) and `verify.sh` (the verification script).

## Exercises

1. **Compute the maxconn for 50,000 concurrent users.** Each user opens 2 connections (HTTP and WebSocket). Each backend has 10,000 maxconn. What is the HAProxy maxconn?

2. **Design the health check for an API that requires a database query.** What is the request? What is the expected response? What is the failure threshold?

3. **Session affinity for a stateful app.** A Java app stores session data in HttpSession (in-memory). Which affinity method (source IP, cookie, header) is appropriate? What is the cookie name? What is the expire time?

4. **Cipher list and the PCI-DSS requirement.** PCI-DSS requires TLS 1.2 or higher, and disallows RC4, 3DES, and MD5-based MACs. Build a cipher list that meets the requirement.

5. **HSTS and the subdomain rule.** HSTS is set with `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`. What does `includeSubDomains` do? What does `preload` do?

6. **Backend drain for maintenance.** A backend needs to be taken out for a security patch. What is the HAProxy command to drain the backend gracefully (existing connections complete, no new connections)?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| HAProxy | "The fast L7 proxy" | The high-availability proxy: an L4/L7 load balancer with sub-millisecond decision time |
| Frontend | "The listening side" | A HAProxy section that binds to a port and routes to a backend |
| Backend | "The server pool" | A HAProxy section that contains the server list and the load-balancing algorithm |
| Active health check | "A probe sent on a timer" | A HAProxy feature that sends a synthetic request to the backend on a regular interval |
| Passive health check | "Watch the live traffic" | A HAProxy feature that monitors live traffic for failed responses and marks the backend down |
| Stick-table | "The session-affinity state" | A HAProxy in-memory data structure that tracks the affinity mapping |
| Source IP affinity | "Same IP, same backend" | A stick-table keyed on the source IP |
| Cookie affinity | "Same cookie, same backend" | A stick-table keyed on a cookie set by HAProxy |
| TLS termination | "End the TLS at the proxy" | The HAProxy handles the TLS handshake and forwards the unencrypted request to the backend |
| HSTS | "Force HTTPS" | HTTP Strict Transport Security: a header that tells the browser to use HTTPS for the next N seconds |

## Further Reading

- **HAProxy 2.8 documentation** — the official HAProxy docs
- **HAProxy Configuration Manual** — the `haproxy.cfg` reference
- **HAProxy Stats documentation** — the stats page reference
- **HAProxy Sticky Sessions** — the stick-table reference
- **RFC 5246, 8446** — *TLS 1.2 / TLS 1.3* — the TLS specifications
- **RFC 6797** — *HTTP Strict Transport Security (HSTS)* — the HSTS specification
- **OWASP TLS Cheat Sheet** — modern TLS configuration
- **Mozilla SSL Configuration Generator** — the de-facto TLS configuration reference
- **HAProxy Prometheus exporter** — the open-source exporter
- **HAProxy Datadog Agent integration** — the Datadog integration
- **HAProxy Enterprise documentation** — the commercial version's features
- **Willy Tarreau's blog** — the HAProxy author's blog
