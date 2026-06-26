#!/bin/bash
# TLS certificate renewal runbook for Compliance Vault
# Cron: 0 3 * * * /opt/scripts/renewal.sh >> /var/log/certbot-renewal.log 2>&1
set -euo pipefail

HOSTNAME="compliance-vault.example.com"
WEBROOT="/var/www/html"

echo "=== $(date -u) : Starting TLS renewal for $HOSTNAME ==="

# 1. Renew via Let's Encrypt (certbot)
certbot renew \
    --cert-name "$HOSTNAME" \
    --webroot --webroot-path "$WEBROOT" \
    --post-hook "systemctl reload nginx"

# 2. Verify the new leaf certificate
openssl x509 \
    -in /etc/letsencrypt/live/$HOSTNAME/cert.pem \
    -noout -subject -issuer -dates

# 3. Verify chain-of-trust
openssl verify \
    -CAfile /etc/letsencrypt/live/$HOSTNAME/chain.pem \
    /etc/letsencrypt/live/$HOSTNAME/cert.pem

# 4. Query OCSP status
openssl ocsp \
    -issuer /etc/letsencrypt/live/$HOSTNAME/chain.pem \
    -cert   /etc/letsencrypt/live/$HOSTNAME/cert.pem \
    -url    "$(openssl x509 -in /etc/letsencrypt/live/$HOSTNAME/cert.pem \
               -noout -ocsp_uri)" \
    -resp_text 2>&1 | grep -E "(Cert Status|This Update|Next Update)"

# 5. Confirm stapled response is visible (requires NGINX reload above)
echo "Verifying OCSP staple..."
openssl s_client \
    -connect $HOSTNAME:443 \
    -servername $HOSTNAME \
    -status \
    </dev/null 2>&1 | grep -E "(OCSP response|Cert Status)"

echo "=== Renewal complete for $HOSTNAME ==="

# --- Revocation runbook (key compromise) ---
# 1. revoke:   certbot revoke --cert-path /etc/letsencrypt/live/$HOSTNAME/cert.pem
# 2. new key:  certbot certonly --key-type ecdsa --elliptic-curve secp384r1 ...
# 3. deploy:   systemctl reload nginx
# 4. verify:   openssl s_client -connect $HOSTNAME:443 -status
