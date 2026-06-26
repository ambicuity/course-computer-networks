# BSR / RP Design Report

- Group range: `239.16.32.0/24`
- Anycast-RP: `10.255.255.1/32`
- Physical RPs: 6
- BSR hash-mask: 30
- SPT switchover: 1000 kbps for 100 s (grace 60 s)
- RPT bandwidth estimate: 700.0 Mbps
- SPT bandwidth estimate: 25.0 Mbps
- Estimated savings: 675.0 Mbps

## RP-to-group mapping (first 16 groups)

| Group | Primary RP | Priority | Backup RP |
|-------|------------|----------|-----------|
| 239.16.32.0 | rp-dc2-1 | 180 | rp-dc1-1 |
| 239.16.32.1 | rp-dc2-1 | 180 | rp-dc1-1 |
| 239.16.32.2 | rp-dc2-1 | 180 | rp-dc1-1 |
| 239.16.32.3 | rp-dc2-1 | 180 | rp-dc1-1 |
| 239.16.32.4 | rp-dc1-1 | 200 | rp-dc3-2 |
| 239.16.32.5 | rp-dc1-1 | 200 | rp-dc3-2 |
| 239.16.32.6 | rp-dc1-1 | 200 | rp-dc3-2 |
| 239.16.32.7 | rp-dc1-1 | 200 | rp-dc3-2 |
| 239.16.32.8 | rp-dc3-1 | 160 | rp-dc2-2 |
| 239.16.32.9 | rp-dc3-1 | 160 | rp-dc2-2 |
| 239.16.32.10 | rp-dc3-1 | 160 | rp-dc2-2 |
| 239.16.32.11 | rp-dc3-1 | 160 | rp-dc2-2 |
| 239.16.32.12 | rp-dc2-1 | 180 | rp-dc2-2 |
| 239.16.32.13 | rp-dc2-1 | 180 | rp-dc2-2 |
| 239.16.32.14 | rp-dc2-1 | 180 | rp-dc2-2 |
| 239.16.32.15 | rp-dc2-1 | 180 | rp-dc2-2 |
