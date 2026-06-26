# Mobile Code Security

> Mobile code is any program that crosses a trust boundary to run on a host that did not author it: Java applets loaded into a browser JVM, Authenticode-signed ActiveX controls, JavaScript executing in a renderer's V8/SpiderMonkey isolate, browser extensions that become part of the trusted computing base, and self-replicating viruses delivered by attachment or drive-by. The four big defensive techniques are (1) the **Java applet sandbox** with a bytecode verifier, security manager, and class-loader namespaces; (2) **code signing** like Microsoft's Authenticode, which authenticates the publisher but does not constrain what the code does once it runs; (3) the browser **same-origin policy** (RFC 6454) plus **Content Security Policy** (CSP, RFC 9110 §8.8 / W3C CSP3) for scripts; and (4) **browser extension isolation** through manifest scopes, host_permissions, and process-per-origin architectures like Chromium's site isolation. Each makes a different trust wager: sandboxing trusts the runtime to constrain behavior, code signing trusts the publisher, origin policies trust the URL identity. Code/main.py implements a stdlib Python 3 simulator that exercises an applet sandbox permission table, a same-origin checker, an Authenticode-vs-sandbox comparison matrix, and a threat taxonomy you can extend when triaging an incident.

**Type:** Learn
**Languages:** Python (stdlib sandbox simulator + origin checker), SVG diagrams, browsers, Wireshark
**Prerequisites:** Phase 16 lessons 1-6 (IPsec, firewalls, wireless, PGP/SMIME, threats, secure naming/SSL); basic familiarity with JavaScript, Java, and PKI certificates
**Time:** ~85 minutes

## Learning Objectives

- Classify each mobile-code technology (Java applet, ActiveX control, JavaScript, browser extension, virus) by trust model: runtime-enforced sandbox vs. publisher trust vs. origin policy vs. none.
- Trace a request through the **Java applet sandbox** security manager and explain why `setSecurityManager(null)` or a misconfigured policy file collapses the boundary.
- Apply the **same-origin policy** triplet (scheme + host + port, RFC 6454 §3) to determine whether a script in tab A can read DOM, cookies, or fetch responses from tab B, and list the cross-origin relaxation mechanisms (CORS, postMessage, document.domain) along with their pitfalls.
- Evaluate **Authenticode** as a trust mechanism: list exactly what a valid signature proves (publisher identity, code unmodified in transit) and what it does *not* prove (code is non-malicious, publisher is currently trustworthy).
- Diagnose mobile-code incident reports by mapping observed IOCs (sandbox escape, cross-origin XHR, malicious signed binary, extension exfiltration) to one of the four defensive models.

## The Problem

A user lands on `news-of-the-day.example`, which embeds a banner ad served from `ads.tracker.example`. The banner contains an SVG file with embedded JavaScript that reaches into the parent document's DOM and reads the user's session cookie for `bank.example`, which is open in another tab. The bank's CSRF token is captured. By the time the SOC analyst opens the browser console, the JavaScript has already fired a cross-origin `fetch()` to the bank's transfer endpoint with the user's cookies attached.

This is not a single bug — it is the canonical failure of the **same-origin policy** (SOP) under modern cross-origin embedding. Twenty years earlier, the same attack pattern would have been a Java applet that called `System.setSecurityManager(null)` and then `Runtime.getRuntime().exec("rm -rf /")`, exploiting the **sandbox model**. A decade before that, it would have been an ActiveX control with a valid Authenticode signature that formatted the disk, exploiting **code signing**. Each era's mobile-code story looks superficially different, but every story is the same wager: how does the host extend trust to a program it did not author?

The lesson's job is to give you a precise vocabulary for the wager, a simulator you can run to *see* the sandbox and origin tables in action, and a runbook for triaging incidents that involve mobile code.

## The Concept

The Java sandbox gives you the cleanest model because it is the most explicit: every privileged operation (file I/O, network, native library load, reflection access to private fields) passes through a `SecurityManager.checkXxx(...)` call that consults a policy file. The browser security manager has no policy file but has the same shape: every cross-origin read or write passes through an origin check, and every powerful API (clipboard, fullscreen, USB) passes through a permission prompt. ActiveX replaces the runtime check with a one-shot publisher check at install time: valid signature and trusted root ⇒ run with the user's full privileges; otherwise abort. The SVG shows the four mechanisms side by side; `code/main.py` runs a simulator for each.

### The Java applet sandbox

A Java applet is shipped as a `.class` file containing **JVM bytecode**. Before any instruction runs, the **bytecode verifier** walks the code and proves three things: (1) every `new` and `astore` have matching types; (2) every method call has the right number of arguments of assignable types; (3) no stack underflow/overflow. A verifier pass that fails aborts the applet; this is what stopped the late-1990s stack-overflow exploits against Microsoft's VM and early Sun JVMs.

Once verified, the applet runs inside an **interpreter** (modern HotSpot still uses an interpreter as the tier-0 entry). Every privileged operation goes through a `SecurityManager` — `checkRead`, `checkWrite`, `checkConnect`, `checkExec`, `checkListen`, `checkPropertyAccess`, etc. The manager reads a `java.policy` file describing *which* code origins (signed-by-whom, from-which-URL) may invoke *which* operations.

The default applet policy, frozen in the early JDK 1.1 days, gives untrusted remote applets a remarkably tight sandbox:

| Operation | Untrusted (remote) | Trusted (local) |
|---|---|---|
| Read files in the JAR's own codebase | allowed | allowed |
| Open a network socket to the originating host | allowed | allowed |
| Read or write the user's local filesystem | denied | allowed |
| `System.setSecurityManager(null)` | denied | allowed |
| `Runtime.exec(...)` / `ProcessBuilder` | denied | allowed |
| Load a native library via `JNI` | denied | allowed |
| Access the system clipboard | prompt | allowed |
| Print | prompt | allowed |

The `setSecurityManager(null)` row is the existential one: a successful call replaces the policy with "no policy," and from that point every privileged call returns silently. Bugs that let attacker-controlled bytecode reach this call (through verifier holes in old JVMs, reflection tricks, or class-loader confusion) are *the* classic applet sandbox escape.

In 2017 Oracle deprecated the Java browser plugin and in 2019 removed it from JDK 11. The browser-side **JavaScript engine** replaced applets, and the Java sandbox model was reborn in the browser as the **same-origin policy plus CSP**, applied to script execution rather than bytecode.

### ActiveX and Authenticode: trust the publisher

ActiveX controls are x86 (and later x64) binary COM objects, downloaded as part of a web page or as a standalone installer. There is no interpreter, no bytecode verifier, no per-call security manager — when the control's `DllRegisterServer` runs, it has the full privileges of the user who triggered the install.

Microsoft's defensive model is **Authenticode**: each control is paired with a digital signature over the control's hash. The signature is verified at install time (and, for some controls, on every load). Verification proves two things and only two things:

1. The publisher who countersigned the hash is who they claim to be (their certificate chains to a root the browser/OS trusts).
2. The control has not been modified since signing.

It does *not* prove the publisher is honest, currently solvent, security-conscious, or even still in business. A signed control can still be malware. In 2001 Fred McLain demonstrated this by forming "UnSANCTIONED Software," getting an Authenticode certificate from a friendly CA, and shipping an ActiveX control ("Download.ject") that, when loaded, performed a clean shutdown of the user's machine. The CA revoked the certificate, but the control had already spread.

The lesson is structural: code signing is a **publisher-trust** mechanism, not a **behavior-trust** mechanism. Compare to the Java sandbox, which is **behavior-trust** with no opinion about who wrote the code.

### JavaScript, same-origin policy, and CSP

JavaScript does not have a bytecode verifier (modern engines compile after parsing), and code signing was abandoned for scripts in the early 2000s. Browsers therefore enforce a different kind of boundary: the **same-origin policy**, codified in RFC 6454. Two pages share an origin iff their **scheme**, **host**, and **port** all match character-for-character (host comparison is case-insensitive, scheme is case-insensitive, port defaults apply: 80 for http, 443 for https).

| Tab A origin | Tab B origin | Same-origin? | What A may read from B |
|---|---|---|---|
| `https://example.com:443` | `https://example.com:443` | yes | DOM, cookies, storage, fetch response |
| `https://example.com:443` | `http://example.com:80` | no (scheme) | nothing |
| `https://example.com:443` | `https://api.example.com:443` | no (host) | nothing |
| `https://example.com:443` | `https://example.com:8443` | no (port) | nothing |
| `https://example.com:443` | `https://attacker.com:443` | no (host) | nothing |

Note that origin does **not** include the path. Two pages on `https://example.com/admin` and `https://example.com/public` are same-origin, even though one is privileged and the other is not. This is why path-prefixes are not a security boundary and you should not rely on them.

When sites genuinely need cross-origin access (a public API, a CDN-loaded font, an embedded widget) the SOP is relaxed by **CORS** (Cross-Origin Resource Sharing, Fetch Living Standard). The server adds an `Access-Control-Allow-Origin: https://app.example.com` header; the browser enforces it. Pitfalls:

- `Access-Control-Allow-Origin: *` + credentials is rejected by the spec; wildcard is only for non-credentialed requests.
- `Access-Control-Allow-Origin: null` is sometimes accepted by old browsers and is a frequent source of bypasses.
- Reflecting the request's `Origin` header verbatim without an allow-list is the canonical CORS misconfiguration.

When SOP is too restrictive for same-page collaboration (iframes, popups), scripts use `window.postMessage(...)` with an explicit `targetOrigin` argument. Forgetting `targetOrigin` and passing `"*"` is the symmetric mistake: any listening window can read the message.

**Content Security Policy (CSP)** is layered on top of SOP, declared in a response header (`Content-Security-Policy: default-src 'self'; script-src 'self' cdn.example.com; object-src 'none'; base-uri 'none'`) and enforced by the browser before each script execution. A reasonable starter policy:

```text
default-src 'self';
script-src 'self' 'nonce-{random}';
style-src 'self' 'nonce-{random}';
img-src 'self' data:;
connect-src 'self' api.example.com;
object-src 'none';
base-uri 'none';
frame-ancestors 'none';
```

`'nonce-{random}'` (a per-response cryptographic nonce in the header and a matching `nonce="..."` attribute on every legitimate `<script>`) is the modern defense against reflected XSS — it makes inline scripts that the server did not authorize impossible to inject.

### Browser extensions: a sixth model

Browser extensions occupy yet another trust tier. A Chrome extension declared in `manifest.json` v3 runs in a service worker plus extension pages, has its own origin (`chrome-extension://<extension-id>`), and gets host permissions via `"host_permissions": ["https://*.example.com/*"]`. The user grants those permissions at install time; the extension can then inject content scripts into matching pages with full DOM access.

The failure modes:

1. **Excessive permissions** — an extension that wants to "decorate your new tab page" but requests `<all_urls>` host permission is the textbook pattern.
2. **Supply-chain compromise** — the maintainer is benign, but their build pipeline or library dependency is hijacked (this happened to several popular Chrome extensions in 2020-2022 by attackers buying or compromising developer accounts).
3. **Logic-level exfiltration** — the extension reads the DOM of every page you visit and `fetch()`es it to a server. This is *exactly* what it claims to do in its privacy policy, but the policy is unread.

Chromium's defense in depth: each origin runs in a separate process (site isolation, since Chrome 67), so a JS sandbox escape in one origin cannot read another origin's memory. Extensions run with their own per-extension origin and a separate process group.

### Viruses: the absent model

A virus is mobile code that **replicates itself**, typically by infecting executable files or boot sectors and propagating via email, removable media, or network shares. The 2000s ILOVEYOU worm reached 45 million machines in one day; the 2017 WannaCry worm encrypted 230,000 hosts across 150 countries in a weekend. Viruses are the only mobile-code category that bypasses the user's consent entirely: there is no "install," no "approve this permission," no "is this publisher trusted" prompt.

The structural defense against viruses is operating-system level: **secure boot** (UEFI verifies the bootloader signature before executing), **TPM-backed measured boot** (attests the boot chain to a remote verifier, per TCG TPM 2.0 spec), and **process isolation** under a microkernel. The academic ideal — capability-based OSes like seL4 or Capsicum — is mostly research; the deployed ideal is "macOS/iOS-style app sandbox + signed binaries + App Store review + per-app entitlements."

## Build It

`code/main.py` ships four independent demonstrators wired into one CLI:

1. **Java sandbox permission table** — prints the untrusted-vs-trusted privilege matrix above.
2. **Same-origin checker** — given two URLs, applies RFC 6454's scheme+host+port rule and returns SAME_ORIGIN or CROSS_ORIGIN with the reason.
3. **ActiveX-vs-sandbox comparison** — prints the trust-model, execution boundary, code verification, default privilege, and typical exploit rows.
4. **Threat taxonomy** — prints the five-category threat list with concrete IOCs.

Run `python3 code/main.py` to see the tables; change the origins at the bottom of `demo_same_origin_policy()` to test your own URLs.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify a mobile-code technology | Trust model (sandbox / publisher / origin / none) | You can name the model and the operation that would defeat it |
| Read an incident report | IOC category (sandbox escape, cross-origin XHR, signed-but-malicious, supply-chain) | You map the IOC to the trust model that failed |
| Configure a sandbox policy | `java.policy` grants | Reads match the principle of least privilege for the code origin |
| Audit a CSP | Header value vs. content the page actually loads | Every inline script has a matching nonce; no `unsafe-inline`; no wildcards |
| Diagnose a CORS error | Browser console error message + response headers | You read the rejection cause (`*` + credentials, missing allow-origin, wrong method) |

Wireshark filter for Authenticode signature verification: `http.response and tcp.stream eq <id>` and inspect the `Content-Type` and signature headers in the response. For same-origin testing in a browser, open DevTools → Console and run `document.origin` to print the current page's serialized origin per HTML Living Standard §7.7.3.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **sandbox-vs-origin-vs-signing decision matrix** your team can paste into a PR review checklist (rows: applets, ActiveX, JS, extensions, viruses; columns: trust model, default privilege, what proves it safe, what defeats it).
- A **same-origin policy cheat sheet** with the (scheme, host, port) triplet, the CORS pitfalls list, and a starter CSP that rejects inline scripts unless explicitly nonced.
- An **Authenticode audit checklist** that names exactly which properties a signature verifies (publisher identity, byte-identity of the code) and which it does not (publisher honesty, code safety, current status of the publisher).
- The **sandbox simulator** (`code/main.py`) wired to your team's incident-response wiki.

Start from `outputs/prompt-mobile-code-security.md`.

## Exercises

1. A junior engineer proposes that "we should make all our applets trusted so they don't get blocked by the sandbox." List three concrete ways that change expands the attack surface and one way it might still fail to help.
2. A page at `https://app.example.com/dashboard` makes a `fetch('https://api.example.com/users')` and gets `Access-Control-Allow-Origin: https://app.example.com` back, but the request fails in the browser. Identify the most likely cause (hint: the engineer forgot one of the four CORS request/response components).
3. An ActiveX control shipped in 2018 is signed with a 2008 certificate. The CA is still in the Windows root store, the certificate has not expired, and the signature verifies. List three reasons the control might still be unsafe to install today.
4. A web extension requests the `"tabs"`, `"storage"`, and `"<all_urls>"` permissions. The store description says "we just want to manage your bookmarks." Identify the two permission scopes that are inconsistent with the stated purpose and the threat they enable.
5. A bank's CSP begins with `default-src 'self' 'unsafe-inline' 'unsafe-eval'`. Explain what each of the three relaxation tokens allows, name the attack class that each one reintroduces, and rewrite the policy in the stricter form.
6. Run `code/main.py`'s same-origin demo with `Origin("https", "example.com", 443)` against (a) `Origin("https", "example.com", 443)`, (b) `Origin("HTTPS", "EXAMPLE.com", 443)`, (c) `Origin("https", "example.com:443", 443)`. Report the verdict for each and explain.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Mobile code | "code that runs in a browser" | Any program that crosses a trust boundary to execute on a host that did not author it: applets, ActiveX, scripts, extensions, viruses |
| Sandbox | "a safe place to run code" | A runtime enforcement layer (Java SecurityManager, browser renderer isolate, OS app sandbox) that intercepts privileged operations and consults a policy |
| Bytecode verifier | "a static checker" | JVM/CLR pass that proves type safety, stack safety, and argument arity before any instruction executes |
| Authenticode | "Microsoft code signing" | PKCS#7 detached signature over an executable's hash, verified against the Windows root store; proves publisher and byte-identity, not behavior |
| Same-origin policy | "scripts can't read across domains" | RFC 6454: scheme + host + port must match; scripts may only read same-origin DOM/cookies/storage/responses |
| CORS | "Cross-Origin Resource Sharing" | Server opt-in via `Access-Control-Allow-Origin` response header; spec forbids `*` + credentials |
| CSP | "Content Security Policy" | Response header declaring allowed sources for script/style/img/connect; `nonce-{random}` blocks inline script injection |
| Site isolation | "per-origin process" | Chromium architecture (Chrome 67+) where each origin runs in a separate renderer process, blocking cross-origin memory reads |
| TPM | "Trusted Platform Module" | TCG-spec chip that measures the boot chain and signs the measurements; foundation of measured boot, not user trust |
| Code signing | "the publisher is verified" | Authenticates publisher identity and code integrity; says nothing about publisher intent or current trustworthiness |

## Further Reading

- **RFC 6454** — *The Web Origin Concept* (Barth, 2011). Authoritative SOP definition.
- **Fetch Living Standard** — `fetch.spec.whatwg.org` (WHATWG). CORS request/response algorithm as currently specified.
- **W3C CSP Level 3** — `Content Security Policy Level 3` (2024 draft). Nonce and hash-source syntax for `script-src`.
- **Microsoft Authenticode** — *Introduction to Code Signing* (Microsoft Learn, 2023). What signature verification actually checks.
- **TCG TPM Library Specification 2.0** — Trusted Platform Module, measured boot, attestation flow.
- **Oracle, "Java Applet and Web Start Code Signing"** (Oracle documentation, archived). The deprecated applet-signing model.
- **Chromium, "Site Isolation"** — `chromium.googlesource.com` design doc. Per-origin process architecture.
- Garfinkel, S. with Spafford, G. (2002), *Web Security, Privacy & Commerce*, 2nd ed., O'Reilly — Chapter 5 on JavaScript, Java, and ActiveX security models.
- Schneier, B. (2004), *Secrets and Lies*, Wiley — Chapter 14 on trust, code signing, and digital rights management.
- Anderson, R. (2008), *Security Engineering*, 2nd ed., Wiley — Chapter 12 on copyright, DRM, and trusted computing.
- Fred McLain's "UnSANCTIONED" demonstration (2001) and the Download.ject incident (CVE-2002-0189) — empirical evidence that code signing does not constrain publisher behavior.
