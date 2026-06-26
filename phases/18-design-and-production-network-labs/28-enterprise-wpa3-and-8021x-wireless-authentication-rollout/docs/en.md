# Enterprise WPA3 and 802.1X wireless authentication rollout

> The CFO's laptop joins "ACME-Corp" — the same SSID as the contractor on the loading dock — and is placed on `10.70.0.0/24` with full access to the ERP. The contractor is also on `10.70.0.0/24`. There is no authentication, no per-user authorization, and no per-user VLAN assignment. The SSID is shared and the PSK is on a sticky note in the break room. **WPA2-PSK** (pre-shared key) does not authenticate the user — it authenticates the password that every device knows. **WPA3-Enterprise** with **802.1X** (IEEE 802.1X-2020) and a **FreeRADIUS** backend authenticates each device AND each user with per-user credentials, then assigns a **RADIUS-attribute-driven VLAN** so the contractor lands on `VLAN 200` and the CFO lands on `VLAN 100`. This lesson deploys a 4-node lab (`ap`, `supplicant`, `radius`, `directory`), runs `hostapd` as the WPA3-Enterprise authenticator, `wpa_supplicant` as the client, FreeRADIUS as the AAA server, and an OpenLDAP directory as the credential store. The companion `code/main.py` is the EAP (Extensible Authentication Protocol, RFC 5247) and FreeRADIUS attribute decoder: it parses a RADIUS Access-Accept packet, extracts the tunnel attributes (`Tunnel-Type=VLAN`, `Tunnel-Medium-Type=802`, `Tunnel-Private-Group-ID`), and prints the per-user authorization that the AP enforces. The end state: every device authenticates with its own per-user cert, lands on its assigned VLAN, and the contractor cannot reach `10.70.10.0/24`.

**Type:** Project
**Languages:** Python, shell, hostapd, FreeRADIUS
**Prerequisites:** Phase 09 IPv4 basics, comfort with RADIUS / AAA, basic PKI / X.509 familiarity
**Time:** ~75 minutes

## Learning Objectives

- Build a 4-node lab (`ap`, `supplicant`, `radius`, `directory`) using Linux network namespaces; connect them on `10.70.0.0/24` (control plane) and `10.70.100.0/24` (data plane).
- Configure `hostapd` as the WPA3-Enterprise AP authenticator with `wpa=2 wpa_key_mgmt=WPA-EAP-SUITE-B-192 ieee80211w=2` (the WPA3-Enterprise / 192-bit security mode per the Wi-Fi Alliance).
- Configure `wpa_supplicant` as the client with an EAP-TLS profile (RFC 5216, EAP-Transport Layer Security) — the strongest EAP method, using X.509 client certificates.
- Configure FreeRADIUS 3.x with an LDAP backend (`rlm_ldap`) and `sites-available/default` to delegate authentication to the directory and authorize VLAN assignment via `users` or LDAP group membership.
- Use `code/main.py` to parse a synthetic RADIUS Access-Accept packet (RFC 2865) and extract the Tunnel-attributes (RFC 2868) that drive VLAN assignment.
- Distinguish **WPA2-PSK** (one password for all devices) from **WPA3-Personal (SAE)** (RFC 7664, Simultaneous Authentication of Equals — no offline dictionary attack) from **WPA3-Enterprise (802.1X)** (per-user X.509, per-user VLAN).
- Validate the rollout with `radtest` (FreeRADIUS's CLI test tool) and a `wpa_supplicant` connection log showing the 4-way handshake completing and the EAP-TLS tunnel establishing.

## The Problem

Pre-shared keys (WPA2-PSK, WPA3-Personal/SAE) authenticate a password, not a user. Once the password is shared — by sticky note, by onboarding email, by contractor — every device that knows the password is indistinguishable from every other device that knows it. Per-device authentication requires **802.1X**: the AP becomes a pass-through authenticator that consults a RADIUS server, the client (supplicant) presents an X.509 certificate, and the RADIUS server decides allow/deny/VLAN. The trap is that 802.1X without a CA, without a directory, and without per-user authorization is just WPA2-PSK with extra steps. A production rollout needs three pieces: a PKI (to issue client/server certs), an authenticator (FreeRADIUS), and an authorization source (LDAP / AD / local users file).

## The Concept

### EAP, 802.1X, and the AAA model

**802.1X-2020** is the IEEE standard for port-based network access control. It defines three roles:

1. **Supplicant** (the client) — `wpa_supplicant` on Linux, the OS supplicant on macOS/Windows.
2. **Authenticator** (the AP or switch) — `hostapd` for Wi-Fi, the switch firmware for wired 802.1X (MACsec).
3. **Authentication Server** (the AAA) — FreeRADIUS, Cisco ISE, Microsoft NPS.

The authenticator does not understand credentials — it only relays EAP (RFC 5247) frames between the supplicant and the AS over **RADIUS** (RFC 2865). EAP itself is a transport; the actual method (TLS, TTLS, PEAP, FAST, AKA, SIM) is negotiated.

**EAP-TLS** (RFC 5216) is the strongest EAP method. Both the supplicant and the server present X.509 certificates, mutual authentication occurs inside the TLS tunnel, and the result is a **Master Session Key (MSK)** that the RADIUS server returns to the authenticator for use as the WPA3 keying material.

### WPA3 vs WPA2 — the differences that matter

| | WPA2-Personal (PSK) | WPA2-Enterprise (802.1X) | WPA3-Personal (SAE) | WPA3-Enterprise (802.1X) |
|---|---|---|---|---|
| Auth | shared password | per-user 802.1X | RFC 7664 SAE handshake | per-user 802.1X |
| Offline dictionary | yes (capture+crack) | n/a (no shared key) | **no** (forward secrecy, dragonfly) | n/a |
| Forward secrecy | no | yes (per-session MSK) | yes | yes |
| 192-bit security | no | optional (`wpa_key_mgmt=WPA-EAP-SUITE-B-192`) | no | yes (`WPA-EAP-SUITE-B-192`) |
| Per-user VLAN | no | yes (RADIUS Tunnel-Type) | no | yes |
| Required PMF | optional | optional | **yes** (`ieee80211w=2`) | **yes** |

**SAE** (Simultaneous Authentication of Equals, RFC 7664) replaces the WPA2 4-way handshake with a "dragonfly" key exchange — both sides derive a key without ever transmitting the password, so an offline capture is useless.

### RADIUS attributes that drive VLAN assignment

When FreeRADIUS accepts a user, it returns an **Access-Accept** packet with attributes:

```
Tunnel-Type = VLAN                    (RFC 2868 §3.1)
Tunnel-Medium-Type = 802              (RFC 2868 §3.2)
Tunnel-Private-Group-ID = "100"       (RFC 2868 §3.6)
```

The AP (hostapd) reads these attributes and assigns the supplicant's session to **VLAN 100**. Each user (or user group in LDAP) maps to a different VLAN. The result: per-user network segmentation without per-user SSIDs.

### PKI: certs, CA, and chain validation

EAP-TLS requires a **CA certificate** on both sides, a **server certificate** on the RADIUS server (the AP validates the server cert), and a **client certificate** on the supplicant (the RADIUS server validates the client cert). The CA signs both; the chain is validated at handshake. In production, you issue from your internal CA (Smallstep, `step-ca`, EJBCA, or `openssl-ca`); for the lab, `openssl` self-signed certs are fine. **Do not ship self-signed certs to production** — a real CA gives you revocation (CRL / OCSP, RFC 6960) and a chain that any device can validate without manual trust-store configuration.

## Build It

### Step 1: Build the 4-node lab

```bash
for n in ap supplicant radius directory; do ip netns add $n; done

ip link add veth-a-s type veth peer name veth-s-a
ip link set veth-a-s netns ap
ip link set veth-s-a netns supplicant
ip netns exec ap ip addr add 10.70.0.1/24 dev veth-a-s
ip netns exec ap ip link set veth-a-s up
ip netns exec supplicant ip addr add 10.70.0.20/24 dev veth-s-a
ip netns exec supplicant ip link set veth-s-a up

ip link add veth-a-r type veth peer name veth-r-a
ip link set veth-a-r netns ap
ip link set veth-r-a netns radius
ip netns exec ap ip addr add 10.70.0.2/24 dev veth-a-r
ip netns exec ap ip link set veth-a-r up
ip netns exec radius ip addr add 10.70.0.3/24 dev veth-r-a
ip netns exec radius ip link set veth-r-a up

ip link add veth-r-d type veth peer name veth-d-r
ip link set veth-r-d netns radius
ip link set veth-d-r netns directory
ip netns exec radius ip addr add 10.70.0.4/24 dev veth-r-d
ip netns exec radius ip link set veth-r-d up
ip netns exec directory ip addr add 10.70.0.5/24 dev veth-d-r
ip netns exec directory ip link set veth-d-r up
```

### Step 2: Generate the PKI

```bash
mkdir -p /tmp/pki && cd /tmp/pki

# CA
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout ca.key -out ca.crt \
    -subj "/CN=ACME-Corp-Internal-CA"

# RADIUS server cert (CN must match the hostname the AP calls)
openssl req -newkey rsa:2048 -nodes \
    -keyout radius.key -out radius.csr \
    -subj "/CN=radius.acme.local"
openssl x509 -req -in radius.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out radius.crt -days 365

# Client cert for cfo@acme.local
openssl req -newkey rsa:2048 -nodes \
    -keyout cfo.key -out cfo.csr \
    -subj "/CN=cfo@acme.local"
openssl x509 -req -in cfo.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out cfo.crt -days 365
```

### Step 3: Install FreeRADIUS + LDAP

```bash
ip netns exec radius bash - <<'EOF'
apt-get install -y freeradius freeradius-ldap slapd ldap-utils
cp /tmp/pki/ca.crt /etc/freeradius/certs/
cp /tmp/pki/radius.crt /etc/freeradius/certs/
cp /tmp/pki/radius.key /etc/freeradius/certs/
chown -R freerad:freerad /etc/freeradius/certs/
EOF
```

### Step 4: Configure FreeRADIUS to delegate to LDAP and assign VLAN

```bash
ip netns exec radius bash - <<'EOF'
cat > /etc/freeradius/sites-available/default <<CFG
authorize {
    ldap
    filter_username
    eap
}
authenticate {
    eap
}
post-auth {
    update reply {
        Tunnel-Type = VLAN
        Tunnel-Medium-Type = IEEE-802
        Tunnel-Private-Group-ID := "%{ldap:ldap:///dc=acme,dc=local??sub?(uid=%{User-Name})?memberOf?cn}"
    }
}
CFG

cat > /etc/freeradius/mods-available/ldap <<CFG
ldap {
    server = "10.70.0.5"
    basedn = "dc=acme,dc=local"
    filter = "(uid=%{%{Stripped-User-Name}:-%{User-Name}})"
    tls {
        start_tls = no
    }
}
CFG

freeradius -X &
EOF
```

### Step 5: Populate the LDAP directory

```bash
ip netns exec directory bash - <<'EOF'
cat > /tmp/init.ldif <<LDIF
dn: dc=acme,dc=local
objectClass: top
objectClass: dcObject
objectClass: organization
o: ACME Corp
dc: acme

dn: ou=people,dc=acme,dc=local
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=acme,dc=local
objectClass: organizationalUnit
ou: groups

dn: uid=cfo,ou=people,dc=acme,dc=local
objectClass: inetOrgPerson
uid: cfo
cn: Chief Financial Officer
userPassword: notused-cert

dn: uid=contractor,ou=people,dc=acme,dc=local
objectClass: inetOrgPerson
uid: contractor
cn: Loading Dock Contractor
userPassword: notused-cert

dn: cn=finance,ou=groups,dc=acme,dc=local
objectClass: groupOfNames
cn: finance
member: uid=cfo,ou=people,dc=acme,dc=local

dn: cn=contractors,ou=groups,dc=acme,dc=local
objectClass: groupOfNames
cn: contractors
member: uid=contractor,ou=people,dc=acme,dc=local
LDIF

slapadd -l /tmp/init.ldif -F /etc/ldap/slapd.d
slapd -h "ldap://10.70.0.5/" &
EOF
```

### Step 6: Configure `hostapd` (WPA3-Enterprise)

```bash
ip netns exec ap bash - <<'EOF'
apt-get install -y hostapd
cat > /etc/hostapd/hostapd.conf <<CFG
interface=veth-a-s
driver=wired
ssid=ACME-Corp
wpa=2
wpa_key_mgmt=WPA-EAP-SUITE-B-192
ieee80211w=2
ieee8021x=1
auth_server_addr=10.70.0.3
auth_server_port=1812
auth_server_shared_secret=testing123
ca_cert=/tmp/pki/ca.crt
server_cert=/tmp/pki/radius.crt
private_key=/tmp/pki/radius.key
vlan_file=/etc/hostapd/hostapd.vlan
vlan_bridge=br-vlan
CFG

cat > /etc/hostapd/hostapd.vlan <<VLAN
100       vlan100
200       vlan200
VLAN

hostapd -dd /etc/hostapd/hostapd.conf &
EOF
```

### Step 7: Configure `wpa_supplicant` (the CFO's laptop)

```bash
ip netns exec supplicant bash - <<'EOF'
apt-get install -y wpa_supplicant
cat > /etc/wpa_supplicant/wpa_supplicant.conf <<CFG
network={
    ssid="ACME-Corp"
    key_mgmt=WPA-EAP-SUITE-B-192
    eap=TLS
    identity="cfo@acme.local"
    client_cert="/tmp/pki/cfo.crt"
    private_key="/tmp/pki/cfo.key"
    ca_cert="/tmp/pki/ca.crt"
}
CFG

wpa_supplicant -i veth-s-a -c /etc/wpa_supplicant/wpa_supplicant.conf -dd &
EOF
```

### Step 8: Verify with `radtest` and the parser

```bash
ip netns exec radius radtest cfo@acme.local '' 10.70.0.3 0 testing123
ip netns exec radius radtest contractor@acme.local '' 10.70.0.3 0 testing123
python3 code/main.py
```

Expected parser output (truncated):

```
=== RADIUS ACCESS-ACCEPT DECODER ===
  user=cfo@acme.local  Tunnel-Type=VLAN  Tunnel-Private-Group-ID=finance
    -> assigned VLAN 100 (CFO gets finance subnet)

  user=contractor@acme.local  Tunnel-Type=VLAN  Tunnel-Private-Group-ID=contractors
    -> assigned VLAN 200 (contractor gets restricted subnet)
```

The AP reads these Tunnel-attributes and places the supplicant on the corresponding VLAN — per-user segmentation without per-user SSIDs.

## Use It

| Capability | `code/main.py` (parser) | hostapd 2.10+ | Cisco IOS-XE AAA | Aruba ClearPass |
|---|---|---|---|---|
| WPA3-Enterprise (SUITE-B-192) | n/a (offline) | yes | yes | yes |
| EAP-TLS / mTLS | yes (parsed on success) | yes | yes | yes |
| RADIUS Tunnel-attributes | yes | yes (reads reply) | yes | yes |
| LDAP user lookup | n/a | n/a (defers to FreeRADIUS) | yes | yes |
| Per-user VLAN | yes (decoded) | yes | yes | yes |
| OCSP / CRL revocation | n/a | partial | yes | yes |
| Per-user firewall policy | n/a | yes (via hostapd_clr) | yes | yes |
| Captive-portal fallback | n/a | yes (`wpa_key_mgmt=WPA-EAP`) | yes | yes |

## Ship It

The reusable artifact is the RADIUS Access-Accept decoder in `code/main.py`. Drop it into an AP-fleet audit tool to verify that the VLAN assignment your FreeRADIUS issued matches the policy you intended (the "did the contractor land on VLAN 200?" question). When your RADIUS server emits 8 attributes and the AP only honors 3, the parser shows you which attributes the AP saw and which it silently dropped.

## Exercises

1. **Add a contractor SSID.** Create a second `wpa_supplicant` profile for the contractor and confirm both can authenticate simultaneously to different VLANs.
2. **Reject on missing cert.** Add an LDAP user without a cert to the directory and watch the FreeRADIUS log show "TLS Alert: unknown_ca".
3. **Revoke a cert.** Generate a CRL with `openssl ca -gencrl`, configure FreeRADIUS to check it, and confirm a revoked cert is denied.
4. **Add OCSP.** Stand up an OCSP responder (`openssl ocsp`), point FreeRADIUS at it, and observe the latency cost of OCSP per authentication.
5. **Replace EAP-TLS with EAP-TTLS.** Swap to `eap=TTLS phase2="PAP"` (RFC 5281, tunneled PAP) and confirm username/password inside the TLS tunnel works without a client cert.
6. **802.11w management frame protection.** Add `ieee80211w=2` (PMF-required) and confirm a `wpa_supplicant` with PMF-disabled cannot associate.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| WPA3-Enterprise | "Wi-Fi with 802.1X" | Per-user authentication with X.509 mutual TLS, RADIUS backend, per-user VLAN; replaces shared PSK. |
| 802.1X | "The dot-one-X standard" | IEEE 802.1X-2020 port-based NAC; the supplicant/authenticator/AS model for both wired (MACsec) and wireless (WPA3). |
| EAP-TLS | "Cert-based auth" | RFC 5216 — both sides present X.509 certs inside a TLS tunnel; the strongest EAP method, no password. |
| RADIUS | "AAA server" | RFC 2865 — the AAA protocol 802.1X uses; Access-Request / Access-Accept / Access-Reject with attributes (RFC 2865, RFC 2868). |
| Tunnel-Private-Group-ID | "The VLAN" | RADIUS attribute (RFC 2868 §3.6) — the AP reads this to assign the supplicant to a specific VLAN. |
| SAE | "Dragonfly handshake" | RFC 7664 Simultaneous Authentication of Equals — the WPA3-Personal handshake; no offline dictionary attacks. |
| EAP-SUITE-B-192 | "192-bit security" | The strongest WPA3-Enterprise mode (192-bit minimum, AES-GCM-256, SHA-384); mandated for government / FIPS. |
| hostapd | "Linux AP daemon" | The de facto Linux Wi-Fi AP + 802.1X authenticator; supports WPA3, RADIUS, VLAN assignment. |

## Further Reading

- [IEEE 802.1X-2020](https://standards.ieee.org/ieee/802.1X/7237/) — Port-Based Network Access Control (the standard behind WPA3-Enterprise)
- [RFC 5247](https://www.rfc-editor.org/rfc/rfc5247) — Extensible Authentication Protocol (EAP) Key Management Framework
- [RFC 5216](https://www.rfc-editor.org/rfc/rfc5216) — The EAP-TLS Authentication Protocol
- [RFC 2865](https://www.rfc-editor.org/rfc/rfc2865) — RADIUS (the AAA protocol)
- [RFC 2868](https://www.rfc-editor.org/rfc/rfc2868) — RADIUS Attributes for Tunnel Protocol Support (the VLAN-assignment attributes)
- [RFC 7664](https://www.rfc-editor.org/rfc/rfc7664) — Dragonfly Key Exchange (SAE for WPA3-Personal)
- [Wi-Fi Alliance: WPA3 Specification](https://www.wi-fi.org/discover-wi-fi/security) — the WPA3 specification overview
- [FreeRADIUS documentation](https://freeradius.org/documentation/) — the AAA server this lesson uses
- [`hostapd` documentation](https://w1.fi/hostapd/) — the Linux AP / 802.1X authenticator
- [`wpa_supplicant` documentation](https://w1.fi/wpa_supplicant/) — the Linux client supplicant