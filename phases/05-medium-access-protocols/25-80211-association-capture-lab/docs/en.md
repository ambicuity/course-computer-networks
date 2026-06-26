# Lab: capturing beacon, probe, auth, and association frames in monitor mode

> In this lab we put a WiFi card into **monitor mode** on Linux (`iw phy phy0 interface add mon0 type monitor` or `airmon-ng start wlan0`), set a channel, and use `tshark -i mon0 -w capture.pcap` to record the four management frame types that bring an 802.11 cell into existence: **beacons** (subtype 0x08) that advertise BSSID, SSID, supported rates, and a typical **beacon interval of 100 TU = 102.4 ms**; **probe requests** (0x04) and **probe responses** (0x05) used by clients to discover APs; **authentication** (0x0B) and **deauthentication** (0x0C) exchanges; and **association request / response** (0x00 / 0x01) frames, with **reassociation** (0x02 / 0x03) used during roaming. Every management frame carries a tag-length-value payload of **Information Elements** — tag 0 (SSID), 1 (Supported Rates), 3 (DS Parameter Set, the channel), 5 (TIM), 45 (HT Capabilities), 48 (RSN), 191 (HT Information), and vendor-specific (221) — and Wireshark/tshark can pull them out with display filters like `wlan.fc.type_subtype == 0x08`, `wlan.bssid == aa:bb:cc:dd:ee:ff`, and `wlan.fc.type == 0` to limit the capture to management traffic.

**Type:** Lab
**Languages:** Python, tshark, shell
**Prerequisites:** Linux host with a WiFi adapter that supports monitor mode and packet injection (e.g. Atheros AR9271, Realtek RTL8812AU), `iw`, `iwconfig`, `aircrack-ng` (for `airmon-ng`), `tshark`, `wireshark`, Python 3.10+
**Time:** ~90 minutes

## Learning Objectives

- Put a wireless interface into **monitor mode** using `iw` and `airmon-ng`, fix the channel, and verify the mode with `iw dev mon0 info`.
- Capture the four frame types that build an 802.11 cell — **beacon, probe, auth, association** — and explain what each one contributes to the join sequence.
- Read the **Frame Control** field and decode Type (00 management, 01 control, 10 data) and Subtype (0x08 beacon, 0x04 probe-req, 0x0B auth, 0x00 assoc-req, 0x0C deauth, 0x02 reassoc-req).
- Walk the **Information Element** chain inside a beacon body, identify SSID / Supported Rates / DS Parameter Set / TIM / HT Capabilities / Country / RSN / Vendor Specific, and read their tag numbers.
- Distinguish **capture filters** (`-f` in tshark, BPF syntax) from **display filters** (`-Y`, the Wireshark `wlan.*` language) and write both to isolate one BSSID on one channel.
- Compute the channel-to-frequency mapping for 2.4 GHz (1–14) and 5 GHz (36–165) and explain why DFS channels (52–144) need the **dynamic frequency selection** service.
- Run the four-step workflow (capture → filter → dissect → export) on a real `.pcap` and produce a one-page capture report.

## The Problem

An on-call engineer gets paged: "guest WiFi at building B is down — clients see the SSID but cannot associate." A junior reports "the AP is on channel 36"; another says "no, it's on 149." Both are plausible because the same SSID is broadcast by three APs, one per floor, on different channels. The engineer needs to answer three questions without driving to the site:

1. Is each AP on the channel the configuration says it should be on, and is it actually using 5 GHz (not the 2.4 GHz fallback)?
2. Is a specific client MAC (`aa:bb:cc:dd:ee:ff`) currently associated, or is it roaming between APs (reassociation frames flying back and forth)?
3. Are any clients being **deauthenticated** mid-session, which would point to a DFS radar event or a misbehaving neighbour?

`ping` won't help — ICMP is end-to-end, not link-layer. ARP cache is empty because association never finished. The only tool that answers these is a WiFi card in **monitor mode** running `tshark` with filters that target 802.11 management frames. This lab puts that toolchain together and walks through the four management frame types in order.

## The Concept

A WiFi cell comes into being through a small handshake of **management frames** (Type = 00 in the Frame Control byte). Beacons announce the AP. Probe requests ask "is anyone out there?" Probe responses answer. Authentication runs the credential exchange. Association (or reassociation when roaming) negotiates the connection. Each frame type carries a tag-length-value list of **Information Elements** that fully describe the AP — its SSID, what data rates it supports, what channel it sits on, whether it uses HT/VHT/HE PHY features, what security suite (RSN / WPA2 / WPA3) it requires, and which country it's operating under for regulatory reasons. Capturing these frames is how you audit what an AP is actually doing versus what it was told to do.

The SVG shows the capture topology (laptop with monitor-mode adapter overhearing APs and clients across a few channels) and a per-field walk of a beacon body. `code/main.py` parses those fields out of synthetic frame dumps so you can rehearse the dissect step without hardware.

### Monitor mode on Linux

A WiFi adapter in its normal ("managed") mode discards every frame that isn't addressed to it. **Monitor mode** disables that filter: the radio dumps every frame it can demodulate onto a virtual interface, frame by frame, including those destined for other clients. On Linux you create a monitor interface on top of a physical PHY:

```sh
# Method A: iw (no monitor-mode support needed in driver, supported by most modern mac80211 drivers)
sudo iw phy phy0 interface add mon0 type monitor
sudo ip link set mon0 up
sudo iw dev mon0 set channel 36

# Method B: airmon-ng (part of aircrack-ng, handles driver quirks for older chipsets)
sudo airmon-ng start wlan0     # creates mon0 (or wlan0mon) and brings it up on the current channel
sudo airmon-ng start wlan0 11   # fix channel 11 in 2.4 GHz
```

Verify with `iw dev mon0 info` (look for `type monitor`) and `iwconfig mon0` (Mode: Monitor, Frequency: 5.18 GHz for channel 36). Stop with `sudo airmon-ng stop mon0` and `sudo iw dev mon0 del` — leaving a monitor interface up blocks normal WiFi on that radio.

### Regulatory domain and channel map

A WiFi adapter will not transmit on channels the kernel's regulatory database forbids in your country. Common bands:

| Band | Range (GHz) | Channels | Notes |
|------|-------------|----------|-------|
| 2.4 GHz ISM | 2.400 – 2.495 | 1 – 13 (most regions), 14 (Japan DSSS only) | 802.11 b/g/n/ax; channel 1, 6, 11 are the non-overlapping trio |
| 5 GHz UNII | 5.150 – 5.825 | 36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165 | 802.11 a/n/ac/ax; 52–144 are DFS (radar detection) |
| 6 GHz (WiFi 6E) | 5.945 – 7.125 | 1 – 233 (per-country) | 802.11ax only; can require AFC coordination |

Each channel number maps to a center frequency: `freq = 5000 + 5 * channel` MHz for 5 GHz, `freq = 2407 + 5 * channel` MHz for 2.4 GHz. `code/main.py` carries the table. The Country IE (tag 7) inside a beacon advertises the regulatory string (e.g. "US", "DE", "JP") so stations know which channel set applies; the Transmit Power Control IE (tag 150) and the 802.11h DFS service drive the dynamic channel moves you sometimes see in beacon log diffs.

### Capture filters vs display filters

`tshark` accepts two very different filter languages, and they run at different stages:

| Kind | Syntax | When it runs | Use case |
|------|--------|--------------|----------|
| Capture filter (`-f`) | libpcap / BPF | Kernel drops packets before they hit userspace | Reduce disk I/O on busy radios; "only put beacons on disk" |
| Display filter (`-Y`) | Wireshark `wlan.*` / `frame.*` | After the packet is captured | Slice inside the same `.pcap` without recapturing |

Examples:

```sh
# Capture filter: only management frames (Type 0), any subtype
tshark -i mon0 -f "wlan[0] & 0x0c == 0x00" -w mgmt.pcap

# Display filter: only beacons (subtype 0x08) for a specific BSSID
tshark -r mgmt.pcap -Y "wlan.fc.type_subtype == 0x08 && wlan.bssid == aa:bb:cc:dd:ee:ff"

# Display filter: probe requests with a wildcard SSID
tshark -r mgmt.pcap -Y "wlan.fc.type_subtype == 0x04 && wlan.ssid == \"\""
```

The Wireshark display-filter cheat sheet for this lab:

| Filter | Meaning |
|--------|---------|
| `wlan.fc.type == 0` | All management frames |
| `wlan.fc.type_subtype == 0x08` | Beacons only |
| `wlan.fc.type_subtype == 0x04` | Probe requests |
| `wlan.fc.type_subtype == 0x05` | Probe responses |
| `wlan.fc.type_subtype == 0x0B` | Authentication |
| `wlan.fc.type_subtype == 0x0C` | Deauthentication |
| `wlan.fc.type_subtype == 0x00` | Association request |
| `wlan.fc.type_subtype == 0x01` | Association response |
| `wlan.fc.type_subtype == 0x02` | Reassociation request (roaming) |
| `wlan.bssid == aa:bb:cc:dd:ee:ff` | Frames from/to one AP |
| `wlan.ssid == "Guest-WiFi"` | Frames carrying a specific SSID |
| `wlan.fc.pwrmgt == 1` | Frames from power-save clients |

### The four-step capture workflow

1. **Capture** — put the radio in monitor mode, fix the channel, run `tshark -i mon0 -w capture.pcap -c 200` (200 frames, or use `-a duration:60` for a 60-second window). For roaming investigations, hop channels with a small script — 1 second per channel across 1, 6, 11 (2.4 GHz) or 36, 40, 44, 48 (5 GHz).
2. **Filter** — open the `.pcap` in Wireshark and apply a display filter, or use `tshark -r capture.pcap -Y "wlan.fc.type_subtype == 0x08"`. The display filter never mutates the file.
3. **Dissect** — click a frame, expand the IEEE 802.11 Beacon frame panel, expand the "Tagged parameters" subtree. Wireshark decodes every IE for you. For automation, `tshark -r capture.pcap -Y "wlan.fc.type_subtype == 0x08" -T fields -e frame.time_epoch -e wlan.bssid -e wlan.ssid -e wlan.beacon -e wlan.ds.current_channel` prints a CSV-ready summary.
4. **Export** — `File → Export Specified Packets` keeps only the filtered frames; `tshark -r capture.pcap -Y "..." -w filtered.pcap` writes a new capture. Hand the result to the report.

### Information Elements

Every 802.11 management frame body is a flat list of **Information Elements** (IEs) — a 1-byte tag, a 1-byte length, and `length` bytes of payload. The standard uses about 70 tag numbers; here are the ones you will see on every beacon:

| Tag | Name | What it carries |
|-----|------|-----------------|
| 0 | SSID | Network name (0–32 bytes; broadcast SSIDs are zero-length) |
| 1 | Supported Rates | Up to 8 legacy rates in 500 kbps units (e.g. `0x0c 0x12 0x18 0x24 0x30 0x48 0x60 0x6c` = 6, 9, 12, 18, 24, 36, 48, 54 Mbps) |
| 3 | DS Parameter Set | Current channel (1 byte) |
| 5 | TIM | Traffic Indication Map — which power-save clients have buffered frames |
| 7 | Country | Regulatory string + subbands of allowed channels / power |
| 45 | HT Capabilities | 802.11n PHY capabilities (channel width, MIMO, short GI) |
| 48 | RSN | WPA2 / WPA3 cipher and AKM suites |
| 50 | Extended Supported Rates | Rates beyond the eight that fit in tag 1 |
| 61 | HT Operation | The AP's view of the 11n operating mode for the current channel |
| 70 | RM Enabled Capabilities | 802.11k radio measurement support |
| 100 | RM Enabled Capabilities (AC) | 802.11ac measurement advertising |
| 127 | Extended Capabilities | Bit-flags for newer features |
| 150 | Transmit Power Envelope | Per-band max EIRP, used with 802.11h / 802.11ax 6 GHz |
| 191 | HT Information | 802.11n BSS-wide HT parameters (used in 5 GHz beacons) |
| 221 | Vendor Specific | Microsoft WPS (00:50:f2:04), Broadcom, Aruba, Cisco, etc. |

`code/main.py` parses tag, length, and payload for any IE and pretty-prints the most common ones.

### Frame subtype hex codes

The lower byte of Frame Control holds Type (2 bits) and Subtype (4 bits). The 4-bit subtype is shifted left by 4 and ORed with Type to produce the value you see in `wlan.fc.type_subtype`:

| Subtype (hex) | Frame |
|---------------|-------|
| 0x00 | Association Request (Req) |
| 0x01 | Association Response (Resp) |
| 0x02 | Reassociation Request |
| 0x03 | Reassociation Response |
| 0x04 | Probe Request |
| 0x05 | Probe Response |
| 0x08 | Beacon |
| 0x09 | ATIM (Ad-hoc Traffic Indication Map) |
| 0x0A | Disassociation |
| 0x0B | Authentication |
| 0x0C | Deauthentication |
| 0x0D | Action (radio / spectrum measurement) |
| 0x0E | Action No Ack |

### Beacon interval, capability, and PHY hints

A beacon body opens with fixed fields before the IE chain:

- **Timestamp** — 8 bytes; the AP's TSF counter at transmission. Stations sync their own clock to this.
- **Beacon Interval** — 2 bytes; how often this beacon appears, in **Time Units (TU)**. 1 TU = 1024 µs, so the de facto default `0x0064` (100 decimal) is **102.4 ms** — about 10 beacons per second. Some enterprise APs go to 200 ms or 300 ms to reduce airtime.
- **Capability Information** — 2 bytes; bit flags for ESS, IBSS, CF-Pollable, CF-Request, Privacy (WEP/WPA), Short Preamble, PBCC, Channel Agility, Spectrum Management, Short Slot Time, and so on.
- **SSID, Supported Rates, ...** — the IE chain.

A well-tuned 802.11ax beacon also carries **BSS Load** (tag 11) with the channel utilization (0–255, scaled as percentage = `util / 255 * 100`) and station count, plus **BSS Color** (inside HE Operation) so neighbours can be filtered at the PHY. These two numbers are how you spot an AP that is over-subscribed without joining it.

## Build It

`code/main.py` is a stdlib-only toolkit with three parts tied to the concept. No `pip install`, no network calls, no pcap library — it parses structured dictionaries or hex strings.

1. **IE parser** — `parse_information_elements(body)` walks the tag-length-value chain and returns `[(tag, payload)]`. A short table maps the common tag numbers to friendly names.
2. **Management-frame parsers** — `parse_beacon()`, `parse_probe_req()`, `parse_auth()`, `parse_assoc_req()` each consume a `dict` describing one frame (timestamp, BSSID, frame control, IE body, channel) and return a typed dataclass with all the fields you'll want to grep for.
3. **Channel-frequency table** — `channel_to_freq()` is the inverse of `freq_to_channel()` for both bands, used by the dissect step to print "channel 36 = 5180 MHz."

Run `python3 code/main.py`. It runs four synthetic frames through the parser and prints a small dissection table. Edit the `SAMPLE_FRAMES` list to plug in a real capture's fields (Wireshark's "Export Packet Bytes" gives you the IE body as hex, which you can hand to `parse_information_elements` directly).

```sh
cd phases/05-medium-access-protocols/25-80211-association-capture-lab
python3 code/main.py
```

## Use It

A toolbox for the on-call engineer:

| Question | Tool / filter | Expected result |
|----------|---------------|-----------------|
| What channel is the AP on? | `tshark -r cap.pcap -Y "wlan.fc.type_subtype==0x08 && wlan.bssid==aa:bb:cc:dd:ee:ff" -T fields -e wlan.ds.current_channel` | One line per beacon: `36` |
| Is the AP in 5 GHz? | `tshark -r cap.pcap -Y "wlan.fc.type_subtype==0x08" -T fields -e wlan.bssid -e wlan.frequency` | `5180` (5 GHz) vs `2437` (2.4 GHz) |
| What SSIDs are nearby? | `tshark -r cap.pcap -Y "wlan.fc.type_subtype==0x08" -T fields -e wlan.ssid` | Sorted unique list |
| Is the client roaming? | `tshark -r cap.pcap -Y "wlan.fc.type_subtype==0x02 && wlan.sa==aa:bb:cc:dd:ee:ff"` | A Reassoc Req every few seconds |
| Is anyone being kicked? | `tshark -r cap.pcap -Y "wlan.fc.type_subtype==0x0c"` | Deauth frames with a reason code in the body |
| Is the AP advertising WPA3? | Open a beacon in Wireshark → Tagged params → RSN. Look for AKM suite `00-0f-ac:8` (SAE) | Confirmed / not present |
| Capture only one channel | `iw dev mon0 set channel 149; tshark -i mon0 -w ch149.pcap` | No frames from other channels |
| Capture all 2.4 GHz channels | Tiny channel-hopping loop (`iw set channel 1; sleep 1; set channel 6; sleep 1; ...`) | Mixed-channel capture in one file |
| Export one BSSID's beacons | `tshark -r cap.pcap -Y "wlan.bssid==aa:bb:cc:dd:ee:ff && wlan.fc.type_subtype==0x08" -w bssid.pcap` | Smaller file for the report |
| Print a CSV | `tshark -r cap.pcap -Y "..." -T fields -E header=y -E separator=, -e frame.time_epoch -e wlan.bssid -e wlan.ssid -e wlan.ds.current_channel` | Pipe into the spreadsheet |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **capture report** — one page that says: when the capture ran, on which adapter (`lsusb` output), on which channels (one row per channel hop), how long (`-a duration:60`), how many frames total, how many of each subtype (`tshark -r cap.pcap -T fields -e wlan.fc.type_subtype | sort | uniq -c`), and a one-line summary of the SSIDs and BSSIDs found. Include the channel utilization reading from the most recent beacon of each AP.
- The **filtered `.pcap`** (one BSSID or one client, depending on the question) handed off alongside the report so anyone can open it in Wireshark and re-dissect.
- The **dissection log** from `code/main.py` running on a few hand-picked frames — useful as a "what good looks like" reference when the next on-call comes looking.

Start from `outputs/prompt-80211-association-capture-lab.md`.

## Exercises

1. **Capture and decode.** Put `mon0` into monitor mode on channel 36, run `tshark -i mon0 -w lab.pcap -a duration:60`, then list every distinct BSSID you saw along with the SSID it advertised. How many distinct SSIDs did you see, and how many APs broadcast an SSID of `0` length (a "hidden" SSID)?
2. **Beacons per second.** Capture for 60 s on a quiet channel. From the beacon interval IE (or by dividing frame count by duration), confirm the typical **100 TU = 102.4 ms** beacon cadence. What is the standard deviation across the APs you found, and why might an AP pick 200 ms instead?
3. **Probe request SSIDs.** Filter for `wlan.fc.type_subtype == 0x04`. Most probe requests include the SSID the client is looking for. Sort the SSIDs by frequency. Why does an AP respond to a probe request that specifies a SSID it doesn't carry?
4. **Roaming trace.** Pick one client MAC from the probe requests. Filter for reassociation requests (`0x02`) from that client over a 5-minute capture. How many distinct BSSIDs did it roam between, and how long did it stay on each? Which BSSID did it land on?
5. **Deauthentication storm.** Filter for `wlan.fc.type_subtype == 0x0c`. Open one frame and read the 2-byte reason code (e.g. `1` = unspecified, `4` = inactivity, `7` = class-3-from-nonassoc, `8` = disassoc due to leaving). Common cause: a misconfigured neighbour AP running a "deauth attack" against foreign MACs. How many unique source MACs sent deauths in 60 s?
6. **Beacon IEs.** From one beacon's IE chain, list every tag number, its length, and a one-line summary of its payload (for example, "tag 48 (RSN), length 20: WPA2-PSK CCMP-128, AKM 00-0f-ac:2"). Which tag is missing from your home AP compared to an enterprise AP?

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|----------------------|
| Monitor mode | "promiscuous for WiFi" | Driver flag that disables destination-address filtering; the radio dumps every demodulated frame to userspace |
| BSSID | "the AP MAC" | The 48-bit MAC address of the AP's wireless interface; appears in every beacon and in Address 2/3 of data frames |
| SSID | "the WiFi name" | Network name; tag-0 IE in beacons and probes; broadcast SSID = empty SSID, not "absent" |
| Beacon | "the heartbeat" | Subtype 0x08 management frame broadcast ~10 times per second; carries timestamp, beacon interval, capability, and the IE chain |
| Beacon interval | "how often" | Two-byte field in the beacon body, units of TU (1024 µs); 100 TU = 102.4 ms |
| Time Unit (TU) | "the 802.11 ms" | 1024 µs — the standard interval unit for beacon interval, listen interval, and most timer fields |
| Information Element (IE) | "the tagged block" | (Tag, Length, Payload) triple inside a management frame body; tag is one byte, length is one byte, payload is `length` bytes |
| Frame Control | "the two-byte header" | First two bytes of every 802.11 frame; carries Type (2 bits), Subtype (4 bits), ToDS, FromDS, Retry, Power Management, More Data, Protected Frame, Order |
| Capture filter | "the BPF" | libpcap filter applied at capture time; `-f` in tshark; discards matching packets before they hit the file |
| Display filter | "the Wireshark one" | The `wlan.*` / `frame.*` language applied after capture; `-Y` in tshark; never mutates the file |
| Probe request | "the scan packet" | Subtype 0x04, sent by a client to discover APs; usually carries the SSID the client is looking for |
| Authentication | "the credential step" | Subtype 0x0B; in WPA2-Personal this is an open-system exchange, in WPA2-Enterprise it triggers EAP over 802.1X |
| Association request | "the join ask" | Subtype 0x00; sent after auth succeeds; carries the client's capabilities and selected rates |
| Reassociation | "the roam" | Subtype 0x02; same as association but includes the Previous AP BSSID, so the new AP can ask the old AP to forward buffered frames |
| Deauthentication | "the boot" | Subtype 0x0C; tears down the relationship without notifying higher layers cleanly (frames are simply dropped after this) |
| RSN | "the WPA2/WPA3 block" | Information Element tag 48; lists cipher suites (e.g. CCMP-128, GCMP-256) and AKM suites (PSK, SAE, 802.1X) |
| HT Capabilities | "the 11n block" | Information Element tag 45; advertises channel width (20/40 MHz), MIMO, short GI, and other 802.11n PHY features |

## Further Reading

- **IEEE 802.11-2007** (and the rolling 802.11-2020 consolidation) — section 7.3 (management frame body, IE format), section 9.4.2 (Information Elements), Annex C (regulatory and channelization).
- **802.11-2016** — adds VHT/HE IE definitions and 802.11ax BSS Color handling.
- **Wireshark 802.11 wiki** — `https://wiki.wireshark.org/HowToDecrypt802.11` and the SSID / BSSID display-filter reference; the canonical display-filter cheat sheet for this lab.
- **`tshark(1)`** man page — every `-f`, `-Y`, `-T fields`, and `-w` flag, plus the full pcap-filter(7) grammar.
- **`iw(8)`** man page — `iw phy`, `iw dev`, `iw reg`, and the regulatory database.
- **Gast, M.** *802.11 Wireless Networks: The Definitive Guide* (O'Reilly, 2005, with later editions) — chapters on frame format, scanning, and the join sequence.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.4 "Wireless LANs" — the source chapter this lesson extends.
