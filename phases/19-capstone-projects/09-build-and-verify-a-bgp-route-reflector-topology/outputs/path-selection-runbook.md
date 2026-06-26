# BGP Best-Path Runbook

1. Highest LOCAL_PREF wins.
2. Shortest AS_PATH wins.
3. Lowest ORIGIN code wins (IGP < EGP < Incomplete).
4. Lowest MED wins.
5. eBGP-learned beats iBGP-learned.
6. Lowest ORIGINATOR_ID (router ID) wins.
7. Lowest neighbor IP wins.

Route reflection adds three rules (RFC 4456): eBGP-to-all, client-to-all, non-client-to-clients-only. Loop guard via ORIGINATOR_ID and CLUSTER_LIST.
