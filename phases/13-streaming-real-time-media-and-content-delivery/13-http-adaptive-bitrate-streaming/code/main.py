"""HTTP Adaptive Bitrate Streaming.

A stdlib-only simulation of an ABR client (like HLS or DASH) that
downloads video segments over HTTP, estimates bandwidth, and switches
quality levels based on buffer state. Demonstrates:

  - Manifest with multiple bitrate variants
  - Bandwidth estimation from download times
  - Buffer-level-driven quality switching
  - A full 30-segment playback session with variable network

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SEGMENT_DURATION = 4.0  # seconds
NUM_SEGMENTS = 30
LOW_WATERMARK = 2.0  # seconds of buffer
HIGH_WATERMARK = 8.0  # seconds of buffer
SAFETY_MARGIN = 0.7  # only use 70% of estimated bandwidth
EWMA_ALPHA = 0.3  # smoothing factor for bandwidth estimate


@dataclass
class Variant:
    """One bitrate variant in the ABR manifest."""
    quality: int
    label: str
    bitrate_kbps: int
    resolution: str


@dataclass
class SegmentDownload:
    """Record of one segment download."""
    segment_idx: int
    quality: int
    label: str
    size_bytes: int
    download_time_s: float
    measured_bw_kbps: int
    buffer_after_s: float
    switch: str  # "up", "down", "same", "rebuffer"


@dataclass
class Manifest:
    """Simulated HLS/DASH manifest with multiple quality variants."""
    variants: List[Variant] = field(default_factory=list)
    segment_duration: float = SEGMENT_DURATION
    num_segments: int = NUM_SEGMENTS

    def segment_size(self, quality: int) -> int:
        """Compute segment size in bytes for a given quality."""
        bitrate_kbps = self.variants[quality].bitrate_kbps
        return int(bitrate_kbps * 1000 * self.segment_duration / 8)


def build_manifest() -> Manifest:
    """Build a manifest with 5 quality levels (like YouTube)."""
    variants = [
        Variant(0, "144p", 150, "256x144"),
        Variant(1, "240p", 400, "426x240"),
        Variant(2, "480p", 1000, "854x480"),
        Variant(3, "720p", 2500, "1280x720"),
        Variant(4, "1080p", 5000, "1920x1080"),
    ]
    return Manifest(variants=variants)


def simulate_network(segment_idx: int) -> int:
    """Return available bandwidth in kbps for a given segment. Varies over time."""
    base = 3000
    # Gradual decline then recovery, plus noise
    wave = 1500 * __import__("math").sin(segment_idx * 0.3)
    noise = random.gauss(0, 300)
    # A bandwidth drop around segment 15-18
    if 15 <= segment_idx <= 18:
        base = 500
    bw = max(100, int(base + wave + noise))
    return bw


class ABRClient:
    """An adaptive bitrate streaming client."""

    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest
        self.current_quality: int = 0
        self.buffer_level: float = 0.0
        self.smoothed_bw: float = 0.0
        self.downloads: List[SegmentDownload] = []
        self.rebuffer_events: int = 0
        self.total_bytes: int = 0
        self.switches: int = 0
        self.playback_started: bool = False

    def estimate_bandwidth(self, measured_bw: int) -> float:
        """Smooth bandwidth estimate using EWMA."""
        if self.smoothed_bw == 0:
            self.smoothed_bw = measured_bw
        else:
            self.smoothed_bw = EWMA_ALPHA * measured_bw + (1 - EWMA_ALPHA) * self.smoothed_bw
        return self.smoothed_bw

    def pick_quality(self) -> int:
        """Select the highest quality sustainable under current bandwidth and buffer."""
        # Panic downgrade if buffer is critically low
        if self.buffer_level < LOW_WATERMARK:
            return max(0, self.current_quality - 1)

        available_bw = self.smoothed_bw * SAFETY_MARGIN
        best = 0
        for v in self.manifest.variants:
            if v.bitrate_kbps <= available_bw:
                best = v.quality
        # Only upgrade if buffer has some headroom (not starving)
        if self.buffer_level < 3.0 and best > self.current_quality:
            best = self.current_quality  # wait for buffer to stabilize
        return best

    def download_segment(self, segment_idx: int) -> SegmentDownload:
        """Simulate downloading one segment and updating state."""
        bw_kbps = simulate_network(segment_idx)
        chosen = self.pick_quality()
        old_quality = self.current_quality

        if chosen < old_quality:
            switch = "down"
        elif chosen > old_quality:
            switch = "up"
        else:
            switch = "same"

        self.current_quality = chosen
        if chosen != old_quality:
            self.switches += 1

        size = self.manifest.segment_size(chosen)
        # Download time: size / bandwidth, but bandwidth is in kbps
        download_time = (size * 8) / (bw_kbps * 1000)

        # Update buffer
        if not self.playback_started:
            # Initial buffering: accumulate buffer before playback starts
            self.buffer_level += self.manifest.segment_duration
            self.playback_started = True
        elif download_time > self.buffer_level + 0.1:
            # Rebuffering: buffer empties during download
            self.rebuffer_events += 1
            self.buffer_level = 0.0
            switch = "rebuffer"
        else:
            # Consume buffer during download, then add segment
            self.buffer_level -= download_time
            self.buffer_level += self.manifest.segment_duration

        # Cap buffer at a maximum
        self.buffer_level = min(self.buffer_level, 30.0)

        # Update bandwidth estimate
        self.estimate_bandwidth(bw_kbps)

        self.total_bytes += size

        record = SegmentDownload(
            segment_idx=segment_idx,
            quality=chosen,
            label=self.manifest.variants[chosen].label,
            size_bytes=size,
            download_time_s=download_time,
            measured_bw_kbps=bw_kbps,
            buffer_after_s=self.buffer_level,
            switch=switch,
        )
        self.downloads.append(record)
        return record

    def play_session(self) -> None:
        """Download all segments and print the session log."""
        print("HTTP Adaptive Bitrate Streaming Simulation\n")
        print(f"Segments: {NUM_SEGMENTS}, duration: {SEGMENT_DURATION}s each")
        print(f"Buffer watermarks: low={LOW_WATERMARK}s, high={HIGH_WATERMARK}s")
        print(f"Safety margin: {SAFETY_MARGIN}, EWMA alpha: {EWMA_ALPHA}\n")

        print("Manifest variants:")
        for v in self.manifest.variants:
            print(f"  Q{v.quality}: {v.label:5s}  {v.bitrate_kbps:5d} kbps  {v.resolution}")
        print()

        print("Session log:")
        print(f"  {'seg':>3}  {'quality':>7}  {'size_KB':>7}  {'dl_s':>6}  {'bw_kbps':>7}  {'smooth_bw':>9}  {'buffer_s':>8}  {'switch'}")
        print("  " + "-" * 75)
        for i in range(NUM_SEGMENTS):
            rec = self.download_segment(i)
            print(
                f"  {rec.segment_idx:3d}  {rec.label:>7}  "
                f"{rec.size_bytes//1024:7d}  {rec.download_time_s:6.2f}  "
                f"{rec.measured_bw_kbps:7d}  {self.smoothed_bw:9.0f}  "
                f"{rec.buffer_after_s:8.1f}  {rec.switch}"
            )
        print()

    def summary(self) -> None:
        """Print session statistics."""
        print("=== Session Summary ===")
        total_played = sum(1 for d in self.downloads if d.switch != "rebuffer")
        quality_counts: Dict[str, int] = {}
        for d in self.downloads:
            quality_counts[d.label] = quality_counts.get(d.label, 0) + 1
        avg_bw = sum(d.measured_bw_kbps for d in self.downloads) / len(self.downloads)
        avg_quality = sum(d.quality for d in self.downloads) / len(self.downloads)

        print(f"  Total segments:      {len(self.downloads)}")
        print(f"  Rebuffer events:     {self.rebuffer_events}")
        print(f"  Quality switches:    {self.switches}")
        print(f"  Total data:          {self.total_bytes / 1e6:.1f} MB")
        print(f"  Average bandwidth:   {avg_bw:.0f} kbps")
        print(f"  Average quality:     {avg_quality:.1f} (0=144p ... 4=1080p)")
        print()
        print("  Quality distribution:")
        for label in ["144p", "240p", "480p", "720p", "1080p"]:
            count = quality_counts.get(label, 0)
            bar = "#" * (count * 2)
            print(f"    {label:5s}: {count:3d} {bar}")
        print()

        print("Key observations:")
        print("  - Player starts at lowest quality (144p) and ramps up")
        print("  - Bandwidth drop at seg 15-18 forces downgrade and rebuffering")
        print("  - EWMA smoothing prevents oscillation during noise")
        print("  - Safety margin (0.7) avoids overestimating available bandwidth")
        print()
        print("Done.")


def main() -> None:
    random.seed(42)
    manifest = build_manifest()
    client = ABRClient(manifest)
    client.play_session()
    client.summary()


if __name__ == "__main__":
    main()
