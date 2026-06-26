"""Mobile Code Security demonstration for Phase 16, Lesson 07.

This module exercises the four trust models for mobile code that crosses a
trust boundary into a host that did not author it:

1. The Java applet sandbox (SecurityManager + bytecode verifier + policy).
2. ActiveX with Authenticode (publisher trust, no behavior monitor).
3. The browser same-origin policy (RFC 6454: scheme + host + port).
4. Browser extensions and Content Security Policy (modern JS world).

Stdlib only. No network calls. No pip dependencies.

Run:  python3 main.py
"""
from __future__ import annotations

import urllib.parse as _u
from dataclasses import dataclass, field
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------


class Decision(Enum):
    """Verdict from a security check."""

    ALLOW = auto()
    DENY = auto()
    PROMPT = auto()


class OriginMismatch(Enum):
    """Reason two origins do not match."""

    SCHEME = "scheme differs (http vs https)"
    HOST = "host differs (different registrable domain)"
    PORT = "port differs (explicit non-default)"


@dataclass(frozen=True)
class Origin:
    """RFC 6454 origin: scheme + host + port."""

    scheme: str
    host: str
    port: int

    def __str__(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


@dataclass(frozen=True)
class SandboxRule:
    """One row of the Java applet sandbox policy."""

    operation: str
    untrusted: Decision
    trusted: Decision


@dataclass(frozen=True)
class Threat:
    """One mobile-code threat category with two example IOCs."""

    category: str
    examples: tuple[str, ...]


# ---------------------------------------------------------------------------
# 1. Java applet sandbox
# ---------------------------------------------------------------------------


JAVA_SANDBOX: tuple[SandboxRule, ...] = (
    SandboxRule("Read file from JAR's own codebase", Decision.ALLOW, Decision.ALLOW),
    SandboxRule("Connect to originating HTTP host", Decision.ALLOW, Decision.ALLOW),
    SandboxRule("Display UI within the browser", Decision.ALLOW, Decision.ALLOW),
    SandboxRule("Read user's local filesystem", Decision.DENY, Decision.ALLOW),
    SandboxRule("Write user's local filesystem", Decision.DENY, Decision.ALLOW),
    SandboxRule("Runtime.exec / ProcessBuilder", Decision.DENY, Decision.ALLOW),
    SandboxRule("System.setSecurityManager(null)", Decision.DENY, Decision.ALLOW),
    SandboxRule("Load native library via JNI", Decision.DENY, Decision.ALLOW),
    SandboxRule("Access system clipboard", Decision.PROMPT, Decision.ALLOW),
    SandboxRule("Print to a local printer", Decision.PROMPT, Decision.ALLOW),
)


def check_sandbox(operation: str, trusted: bool) -> Decision:
    """Return the sandbox decision for a single operation.

    Args:
        operation: Privileged operation name as it would appear in
            ``java.policy`` or a SecurityManager log.
        trusted: ``True`` if the applet was loaded from the local disk and
            signed by a CA the JRE trusts; ``False`` for remote applets.

    Returns:
        The matching Decision. ``PROMPT`` is used for ambiguous operations.
    """
    for rule in JAVA_SANDBOX:
        if rule.operation == operation:
            return rule.trusted if trusted else rule.untrusted
    raise KeyError(f"unknown operation: {operation!r}")


def simulate_applet_session(trusted: bool) -> list[tuple[str, Decision]]:
    """Simulate an applet trying a fixed list of privileged operations.

    Args:
        trusted: Whether the applet is treated as trusted.

    Returns:
        A list of (operation, decision) tuples in the order attempted.
    """
    sequence = [
        "Display UI within the browser",
        "Read file from JAR's own codebase",
        "Connect to originating HTTP host",
        "Read user's local filesystem",
        "Write user's local filesystem",
        "Runtime.exec / ProcessBuilder",
        "System.setSecurityManager(null)",
        "Load native library via JNI",
        "Access system clipboard",
        "Print to a local printer",
    ]
    return [(op, check_sandbox(op, trusted)) for op in sequence]


# ---------------------------------------------------------------------------
# 2. ActiveX / Authenticode
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthenticodeResult:
    """Outcome of an Authenticode signature verification."""

    publisher: str
    signature_valid: bool
    certificate_trusted: bool
    control_byte_identical: bool

    @property
    def will_install(self) -> bool:
        """Return True iff the OS would actually install the control.

        The OS only needs the signature to be valid and the certificate to
        chain to a trusted root. It does not inspect the control's behavior.
        """
        return self.signature_valid and self.certificate_trusted


def authenticate(result: AuthenticodeResult) -> dict[str, str]:
    """Map an Authenticode verification result to a property table.

    The table makes explicit what a signature *proves* and what it does not.
    """
    return {
        "publisher identity confirmed": str(result.signature_valid),
        "control unmodified since signing": str(result.control_byte_identical),
        "publisher cert chains to trusted root": str(result.certificate_trusted),
        "publisher is honest": "FALSE (signature does not prove intent)",
        "publisher still in business": "FALSE (signature does not prove solvency)",
        "control is non-malicious": "FALSE (signature does not prove behavior)",
    }


# ---------------------------------------------------------------------------
# 3. Same-origin policy (RFC 6454)
# ---------------------------------------------------------------------------


def _default_port(scheme: str) -> int:
    """Return the default port for a given scheme (RFC 1700 / IANA)."""
    return {"http": 80, "https": 443, "ws": 80, "wss": 443}.get(
        scheme.lower(), -1
    )


def parse_origin(url: str) -> Origin:
    """Parse an absolute URL into an RFC 6454 origin.

    Args:
        url: Absolute URL with scheme. The path is ignored on purpose —
            the same-origin policy does not consider paths.

    Returns:
        The Origin triple (scheme, host, port).

    Raises:
        ValueError: If the URL has no scheme or no host.
    """
    parsed = _u.urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"not an absolute URL: {url!r}")
    port = parsed.port if parsed.port is not None else _default_port(parsed.scheme)
    return Origin(scheme=parsed.scheme.lower(), host=parsed.hostname.lower(), port=port)


def same_origin(first: Origin, second: Origin) -> tuple[bool, OriginMismatch | None]:
    """Apply RFC 6454's same-origin comparison.

    Two origins are same-origin iff scheme, host, and port all match.
    Hosts are case-insensitive; schemes are case-insensitive; ports are
    compared numerically.

    Args:
        first: First origin.
        second: Second origin.

    Returns:
        A tuple (matches, reason). If ``matches`` is True, ``reason`` is
        None. If False, ``reason`` names the first component that disagreed.
    """
    if first.scheme != second.scheme:
        return False, OriginMismatch.SCHEME
    if first.host != second.host:
        return False, OriginMismatch.HOST
    if first.port != second.port:
        return False, OriginMismatch.PORT
    return True, None


def can_read(first: Origin, second: Origin) -> str:
    """Describe what scripts in origin ``first`` may read from origin ``second``.

    Returns a one-line string a browser console would print, including the
    reason for any cross-origin rejection.
    """
    match, reason = same_origin(first, second)
    if match:
        return f"SAME-ORIGIN: {first} may read DOM, cookies, storage, fetch responses from {second}"
    return (
        f"CROSS-ORIGIN ({reason.value if reason else '?'}): {first} cannot read "
        f"DOM/cookies/storage from {second}; CORS opt-in required for fetch"
    )


# ---------------------------------------------------------------------------
# 4. Threats and CSP
# ---------------------------------------------------------------------------


MOBILE_CODE_THREATS: tuple[Threat, ...] = (
    Threat("Code-signing abuse", (
        "Signed ActiveX control turns malicious after publication (publisher compromise)",
        "Self-signed certificate silently accepted by user",
    )),
    Threat("Sandbox escape", (
        "Java SecurityManager disabled via reflection on private field",
        "Browser renderer 0-day (e.g., V8 type confusion) used to bypass site isolation",
    )),
    Threat("Cross-origin exfiltration", (
        "Misconfigured Access-Control-Allow-Origin reflects any Origin header",
        "postMessage('*') leaks data to any listening window",
    )),
    Threat("Extension supply-chain", (
        "Maintainer account hijacked; update pushed with exfiltration code",
        "Extension requests <all_urls> but only needs a single origin",
    )),
    Threat("Virus / self-replication", (
        "Email attachment with macro that drops loader binary into %APPDATA%",
        "Boot-sector virus infects MBR and persists across OS reinstall",
    )),
)


STARTER_CSP: dict[str, str] = {
    "default-src": "'self'",
    "script-src": "'self' 'nonce-{random-per-response}'",
    "style-src": "'self' 'nonce-{random-per-response}'",
    "img-src": "'self' data:",
    "connect-src": "'self' api.example.com",
    "object-src": "'none'",
    "base-uri": "'none'",
    "frame-ancestors": "'none'",
}


def csp_to_string(policy: dict[str, str]) -> str:
    """Serialize a CSP policy as a response header value."""
    return "; ".join(f"{k} {v}" for k, v in policy.items())


def relaxations_to_attacks(unrestricted: dict[str, str]) -> list[tuple[str, str]]:
    """Map a relaxed CSP policy back to the attack class each token reintroduces.

    Useful for explaining why a ``default-src 'unsafe-inline' 'unsafe-eval'``
    policy is no better than no policy at all.
    """
    attacks: list[tuple[str, str]] = []
    src = unrestricted.get("script-src", unrestricted.get("default-src", ""))
    if "'unsafe-inline'" in src:
        attacks.append(("'unsafe-inline'", "reflected/stored XSS executes inline"))
    if "'unsafe-eval'" in src:
        attacks.append(("'unsafe-eval'", "eval / new Function / setTimeout(string) executes attacker code"))
    if "*" in src:
        attacks.append(("'*' in script-src", "any CDN compromise becomes an XSS on your origin"))
    if "data:" in src and "script-src" not in unrestricted:
        attacks.append(("data: in default-src", "data: URL injection executes script"))
    return attacks


# ---------------------------------------------------------------------------
# 5. ActiveX vs sandbox comparison table
# ---------------------------------------------------------------------------


TRUST_MODEL_COMPARISON: dict[str, dict[str, str]] = {
    "Trust anchor": {
        "Java sandbox": "Runtime (SecurityManager + policy)",
        "ActiveX/Authenticode": "Publisher certificate",
        "Same-origin policy": "URL scheme+host+port (RFC 6454)",
        "Browser extension": "Per-extension origin + manifest permissions",
    },
    "When check runs": {
        "Java sandbox": "Every privileged operation",
        "ActiveX/Authenticode": "At install time (and on each load)",
        "Same-origin policy": "On every cross-origin read or fetch",
        "Browser extension": "At install time (manifest permissions)",
    },
    "What it proves": {
        "Java sandbox": "Operation is in the policy",
        "ActiveX/Authenticode": "Publisher identity + control byte-identity",
        "Same-origin policy": "Two URLs share a security context",
        "Browser extension": "User explicitly granted the listed permissions",
    },
    "What it does NOT prove": {
        "Java sandbox": "Code is well-written or non-malicious within policy",
        "ActiveX/Authenticode": "Publisher is honest; control is safe to run",
        "Same-origin policy": "Same-origin code is trustworthy (e.g., ad iframe)",
        "Browser extension": "Extension logic does not exfiltrate or backdoor",
    },
    "Typical exploit": {
        "Java sandbox": "setSecurityManager(null) via reflection or class-loader confusion",
        "ActiveX/Authenticode": "Trusted publisher ships malicious update",
        "Same-origin policy": "CORS misconfiguration / postMessage('*')",
        "Browser extension": "Supply-chain takeover via developer account",
    },
}


# ---------------------------------------------------------------------------
# CLI demos
# ---------------------------------------------------------------------------


def _print_header(title: str) -> None:
    bar = "=" * 68
    print(f"\n{bar}\n{title.center(68)}\n{bar}")


def demo_java_sandbox() -> None:
    """Print the Java applet sandbox policy and an untrusted applet session."""
    _print_header("Java Applet Sandbox Policy")
    print(f"{'Operation':<48} {'Untrusted':<12} {'Trusted':<12}")
    print("-" * 72)
    for rule in JAVA_SANDBOX:
        print(f"{rule.operation:<48} {rule.untrusted.name:<12} {rule.trusted.name:<12}")

    _print_header("Simulated Untrusted Applet Session")
    print(f"{'Operation':<48} {'Decision':<10}")
    print("-" * 58)
    for op, dec in simulate_applet_session(trusted=False):
        print(f"{op:<48} {dec.name:<10}")


def demo_authenticode() -> None:
    """Show the Authenticode property table for two example controls."""
    _print_header("Authenticode Property Table")
    examples = (
        AuthenticodeResult("Acme Corp", True, True, True),
        AuthenticodeResult("UnSANCTIONED Software", True, True, True),
        AuthenticodeResult("StaleVendor Inc.", True, False, True),
    )
    for ex in examples:
        print(f"\nPublisher: {ex.publisher}  will_install={ex.will_install}")
        for prop, val in authenticate(ex).items():
            print(f"  proves: {prop:<48} = {val}")


def demo_same_origin() -> None:
    """Run RFC 6454 comparisons over a curated URL pair set."""
    _print_header("Same-Origin Policy (RFC 6454)")
    reference = parse_origin("https://example.com/dashboard")
    print(f"reference origin: {reference}\n")
    candidates = (
        "https://example.com/admin",
        "http://example.com/",
        "https://api.example.com/",
        "https://example.com:8443/",
        "https://EXAMPLE.com/",
        "https://attacker.com/",
    )
    print(f"{'URL':<40} {'Verdict':<60}")
    print("-" * 100)
    for url in candidates:
        other = parse_origin(url)
        print(f"{url:<40} {can_read(reference, other)}")


def demo_csp() -> None:
    """Print the starter CSP and explain what a relaxed policy reintroduces."""
    _print_header("Starter Content Security Policy")
    print("HTTP response header:")
    print(f"  Content-Security-Policy: {csp_to_string(STARTER_CSP)}\n")
    print("Each <script> tag the server emits gets a matching nonce attribute:")
    print('  <script nonce="RANDOM123">alert("hi")</script>\n')
    print("Inline scripts injected by an attacker cannot guess the nonce.\n")

    _print_header("What a Relaxed Policy Reintroduces")
    relaxed = {
        "default-src": "'self' 'unsafe-inline' 'unsafe-eval'",
        "script-src": "'self' 'unsafe-inline' 'unsafe-eval'",
    }
    for token, attack in relaxations_to_attacks(relaxed):
        print(f"  {token:<18} -> {attack}")


def demo_threats() -> None:
    """Print the mobile-code threat taxonomy."""
    _print_header("Mobile Code Threat Taxonomy")
    for threat in MOBILE_CODE_THREATS:
        print(f"\n{threat.category}")
        for ex in threat.examples:
            print(f"  - {ex}")


def demo_trust_model_comparison() -> None:
    """Print the trust-model comparison table across all four mechanisms."""
    _print_header("Trust Model Comparison")
    aspects = list(TRUST_MODEL_COMPARISON.keys())
    models = list(next(iter(TRUST_MODEL_COMPARISON.values())).keys())
    col_w = max(len(m) for m in models) + 2
    header = f"{'Aspect':<18}" + "".join(f"{m:<{col_w}}" for m in models)
    print(header)
    print("-" * len(header))
    for aspect in aspects:
        row = f"{aspect:<18}"
        for model in models:
            row += f"{TRUST_MODEL_COMPARISON[aspect][model]:<{col_w}}"
        print(row)


def main() -> None:
    """Run every mobile-code security demonstration in sequence."""
    print("Mobile Code Security Demo")
    print("Models: Java sandbox, ActiveX/Authenticode, SOP, extensions, CSP")
    demo_java_sandbox()
    demo_authenticode()
    demo_same_origin()
    demo_csp()
    demo_threats()
    demo_trust_model_comparison()


if __name__ == "__main__":
    main()
