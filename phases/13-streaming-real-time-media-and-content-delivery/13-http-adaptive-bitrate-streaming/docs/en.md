# HTTP Adaptive Bitrate Streaming

> The player watches its own buffer and switches video quality up and down as bandwidth fluctuates. No special server protocol needed - just HTTP and a manifest file.

**Type:** Build
**Languages:** Python, shell
**Prerequisites:** Phase 13 lessons 01-12 (Streaming Stored Media, HTTP, RTSP)
**Time:** ~75 minutes

## Learning Objectives

- Explain how ABR streaming works over plain HTTP with segmented media
- Describe the manifest formats: HLS (M3U8) and MPEG-DASH (MPD)
- Implement a bandwidth-estimation and quality-switching algorithm
- Trace the client state machine: buffer low -> downgrade, buffer full -> upgrade
- Identify the tradeoffs between HLS and DASH

## The Problem

RTSP requires a specialized streaming server and persistent session state. Modern CDNs want to serve video over plain HTTP caches, because HTTP is already deployed everywhere. The solution: break the video into short segments (2-10 seconds each), encode each segment at multiple bitrates, and let the player download segments over HTTP using a manifest file that lists all available qualities. The player monitors its buffer level and current download throughput, then picks the highest quality it can sustain without rebuffering. This is HTTP Adaptive Bitrate (ABR) streaming, and it powers YouTube, Netflix, and Twitch.

## The Concept

### Architecture

```text
encoder: video -> segments at multiple bitrates (240p, 480p, 720p, 1080p)
  |
  v
manifest: M3U8 (HLS) or MPD (DASH) lists all segments and bitrates
  |
  v
CDN: serves segments as static HTTP files (cacheable)
  |
  v
player:
  1. fetch manifest
  2. estimate bandwidth from segment download time
  3. pick highest sustainable bitrate
  4. download segment, feed buffer
  5. repeat, switching quality as bandwidth changes
```

### HLS (HTTP Live Streaming, Apple)

Uses M3U8 playlist files. A master playlist lists variant streams (different bitrates). Each variant has its own media playlist listing .ts segment URLs. Segments are typically 6-10 seconds. HLS uses TCP (HTTP) for transport.

### MPEG-DASH

Uses an MPD (Media Presentation Description) XML file. Similar structure but more flexible: supports different segment durations, base URLs, and time-shift buffers. DASH is codec-agnostic and ISO standard.

### ABR switching algorithm

The classic algorithm:

1. Measure download throughput: `bandwidth = segment_bytes / download_time`
2. Smooth it with a moving average to avoid oscillation
3. Compute the highest bitrate whose required bandwidth is below `smoothed_bw * safety_margin`
4. If buffer is below a low watermark, switch down immediately
5. If buffer is above a high watermark, try switching up

```text
if buffer < low_watermark:
    quality = max(0, quality - 1)    # panic downgrade
elif buffer > high_watermark and bw > next_bitrate / margin:
    quality = min(max_quality, quality + 1)  # cautious upgrade
```

### Buffer states

| State | Buffer level | Action |
|-------|-------------|--------|
| Starving | < 2s | Downgrade immediately, risk rebuffering |
| Cautious | 2-5s | Stay at current quality |
| Healthy | 5-15s | Consider upgrade if bandwidth allows |
| Full | > 15s | Upgrade aggressively |

## Build It

The script below simulates an ABR client over a variable-bandwidth network. It demonstrates:

1. Manifest parsing (simulated HLS M3U8 structure)
2. Bandwidth estimation from segment download times
3. Quality switching with buffer-level feedback
4. A 30-segment playback session with fluctuating network conditions
5. Statistics: average quality, rebuffer events, total bytes

```python
# Core idea (see code/main.py for full implementation)
for segment in segments:
    bw = estimate_bandwidth(segment)
    quality = pick_quality(bw, buffer_level)
    download_time = segment_size / bw
    buffer_level += segment_duration - download_time
```

## Use It

```bash
python3 code/main.py
```

Expected output: a segment-by-segment log showing bandwidth estimate, chosen quality, buffer level, download time, and any quality switches. A summary reports the average playback quality, number of rebuffer events, and total data consumed.

## Ship It

- Use the script to explain why ABR players start at low quality and ramp up (the "slow start" phase).
- Tune the safety margin and buffer watermarks and observe how they affect oscillation vs stability.
- Compare the results with a real YouTube or Netflix stream by opening browser dev tools and watching network requests.

## Exercises

1. Reduce the safety margin from 0.7 to 0.5 and observe more frequent upswitches. Does rebuffering increase?
2. Increase segment duration from 4s to 10s and show how latency (time to switch quality) increases.
3. Add a network spike (bandwidth drops to 0 for 5 segments) and trace the rebuffer events.
4. Implement a predictive algorithm that uses TCP goodput history to pre-select quality before download.
5. Compare HLS-style fixed segments with DASH-style variable segments and discuss the tradeoffs.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| ABR | "Adaptive streaming" | Adaptive Bitrate Streaming: the player dynamically selects video quality based on measured bandwidth and buffer level |
| Manifest | "Playlist" | A file (M3U8 or MPD) listing all available segments and their bitrates |
| Segment | "Chunk" | A short (2-10s) piece of video encoded as a standalone HTTP file |
| M3U8 | "HLS playlist" | The HLS manifest format, a text playlist listing variant streams or segment URLs |
| MPD | "DASH manifest" | Media Presentation Description, the XML manifest used by MPEG-DASH |
| Buffer watermark | "Buffer threshold" | A buffer-level threshold that triggers quality up/down switching |
| Rebuffering | "Buffering..." | When the buffer empties and playback stalls while waiting for the next segment |
| Safety margin | "Conservative factor" | A multiplier (e.g., 0.7) that prevents switching to a quality too close to the estimated bandwidth |

## Further Reading

- [HTTP Live Streaming (Apple)](https://developer.apple.com/streaming/) - HLS documentation
- [MPEG-DASH standard](https://mpeg.chiariglione.org/standards/mpeg-dash) - DASH overview
- [A Survey on HTTP Adaptive Streaming](https://dl.acm.org/doi/10.1145/2893535) - academic survey of ABR algorithms
