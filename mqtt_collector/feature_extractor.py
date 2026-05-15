"""
NetGuard AI — Phase 2 Feature Extractor
=========================================
Reads raw_telemetry.csv produced by collector.py and applies a sliding
time-window per device to compute aggregated network-behaviour features.

The resulting features.csv is the ACTUAL ML training input — not raw packets.

Usage:
  python feature_extractor.py                        # default 5s window
  python feature_extractor.py --window 10            # 10s window
  python feature_extractor.py --window 5 --step 1   # 5s window, 1s step
"""

import argparse
import csv
import os
import math
from collections import defaultdict
from datetime import datetime, timezone

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(__file__)
DATASET   = os.path.join(BASE_DIR, "dataset")
RAW_CSV   = os.path.join(DATASET, "netguard_dataset.csv")
OUT_CSV   = os.path.join(DATASET, "features.csv")

# ── Feature schema ────────────────────────────────────────────────────────────
FEATURE_COLS = [
    "window_start_utc",      # ISO timestamp of window start
    "window_end_utc",        # ISO timestamp of window end
    "device",                # which device this window belongs to
    "packet_count",          # total packets in window
    "packet_rate",           # packets per second
    "mean_inter_arrival_ms", # average gap between consecutive packets
    "std_inter_arrival_ms",  # std dev of inter-arrival (high = erratic)
    "min_inter_arrival_ms",  # minimum gap (near-0 = flood)
    "max_inter_arrival_ms",  # maximum gap (very high = slow-rate)
    "duplicate_ratio",       # fraction of packets with duplicate seq numbers
    "seq_increment_mean",    # average seq number jump (0 = frozen = replay)
    "seq_increment_std",     # std dev of seq jump
    "unique_modes",          # how many different attack modes appeared
    "dominant_mode",         # most frequent mode in window
    "label",                 # majority ground-truth label for this window
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_ts(ts_str: str) -> float:
    """Parse ISO-8601 UTC timestamp → float epoch seconds."""
    ts_str = ts_str.rstrip("Z")
    # Handle optional fractional seconds
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc).timestamp()


def epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)\
                   .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def safe_mean(values):
    return sum(values) / len(values) if values else 0.0


def safe_std(values):
    if len(values) < 2:
        return 0.0
    m = safe_mean(values)
    variance = sum((x - m) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def majority(items):
    if not items:
        return "UNKNOWN"
    return max(set(items), key=items.count)


# ── Core window computation ───────────────────────────────────────────────────
def compute_features(packets: list, window_start: float, window_end: float,
                     device: str) -> dict:
    """
    Given a list of raw packet dicts within a time window, return one
    feature-row dict.
    """
    n = len(packets)
    duration = window_end - window_start   # seconds

    # ── Inter-arrival times ────────────────────────────────────────────────
    timestamps = sorted(p["_epoch"] for p in packets)
    inter_arrivals = [
        (timestamps[i+1] - timestamps[i]) * 1000.0
        for i in range(len(timestamps) - 1)
    ]

    # ── Sequence number analysis ───────────────────────────────────────────
    seqs = [p["seq"] for p in packets if p["seq"] != -1]
    seq_increments = [seqs[i+1] - seqs[i] for i in range(len(seqs) - 1)]

    seen_seqs = set()
    duplicate_count = 0
    for s in seqs:
        if s in seen_seqs:
            duplicate_count += 1
        seen_seqs.add(s)
    duplicate_ratio = duplicate_count / n if n > 0 else 0.0

    # ── Mode / label distribution ──────────────────────────────────────────
    modes  = [p["mode"]  for p in packets]
    labels = [p["label"] for p in packets]

    return {
        "window_start_utc":      epoch_to_iso(window_start),
        "window_end_utc":        epoch_to_iso(window_end),
        "device":                device,
        "packet_count":          n,
        "packet_rate":           round(n / duration, 4) if duration > 0 else 0,
        "mean_inter_arrival_ms": round(safe_mean(inter_arrivals), 2),
        "std_inter_arrival_ms":  round(safe_std(inter_arrivals), 2),
        "min_inter_arrival_ms":  round(min(inter_arrivals), 2) if inter_arrivals else 0,
        "max_inter_arrival_ms":  round(max(inter_arrivals), 2) if inter_arrivals else 0,
        "duplicate_ratio":       round(duplicate_ratio, 4),
        "seq_increment_mean":    round(safe_mean(seq_increments), 4),
        "seq_increment_std":     round(safe_std(seq_increments), 4),
        "unique_modes":          len(set(modes)),
        "dominant_mode":         majority(modes),
        "label":                 majority(labels),
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main(window_sec: float = 5.0, step_sec: float = 2.5):
    print("=" * 70)
    print("  NetGuard AI — Feature Extractor")
    print(f"  Input  : {RAW_CSV}")
    print(f"  Output : {OUT_CSV}")
    print(f"  Window : {window_sec}s  |  Step : {step_sec}s")
    print("=" * 70)

    if not os.path.exists(RAW_CSV):
        print(f"[!] Raw CSV not found: {RAW_CSV}")
        print("    Run collector.py first to generate data.")
        return

    # ── 1. Load raw CSV ───────────────────────────────────────────────────
    device_packets = defaultdict(list)   # device → list of packet dicts
    total_rows = 0

    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            epoch = parse_ts(row["timestamp_utc"])
            pkt = {
                "_epoch":  epoch,
                "topic":   row["topic"],
                "mode":    row["mode"],
                "label":   row["label"],
                "seq":     int(row["seq"]) if row["seq"] not in ("", "-1") else -1,
            }
            device = row["device"]
            device_packets[device].append(pkt)

    print(f"[+] Loaded {total_rows} raw packets across {len(device_packets)} devices.")

    # ── 2. Slide window per device and extract features ───────────────────
    all_feature_rows = []

    for device, packets in device_packets.items():
        if not packets:
            continue

        packets.sort(key=lambda p: p["_epoch"])
        t_start_global = packets[0]["_epoch"]
        t_end_global   = packets[-1]["_epoch"]

        win_start = t_start_global
        windows_processed = 0

        while win_start + window_sec <= t_end_global + step_sec:
            win_end = win_start + window_sec

            # Collect packets within [win_start, win_end)
            window_pkts = [
                p for p in packets
                if win_start <= p["_epoch"] < win_end
            ]

            # Skip near-empty windows (fewer than 2 packets = no meaningful stats)
            if len(window_pkts) >= 2:
                feat = compute_features(window_pkts, win_start, win_end, device)
                all_feature_rows.append(feat)
                windows_processed += 1

            win_start += step_sec

        print(f"    {device:<14} → {windows_processed} windows extracted")

    # ── 3. Write feature CSV ──────────────────────────────────────────────
    os.makedirs(DATASET, exist_ok=True)
    all_feature_rows.sort(key=lambda r: r["window_start_utc"])

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
        writer.writeheader()
        writer.writerows(all_feature_rows)

    print(f"\n[+] Done! {len(all_feature_rows)} feature-windows written to:")
    print(f"    {OUT_CSV}")

    # ── 4. Label distribution summary ────────────────────────────────────
    label_counts = defaultdict(int)
    for row in all_feature_rows:
        label_counts[row["label"]] += 1

    print("\n    Label distribution:")
    for lbl, cnt in sorted(label_counts.items()):
        pct = 100.0 * cnt / len(all_feature_rows)
        print(f"      {lbl:<22} {cnt:>5} windows  ({pct:.1f}%)")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetGuard Feature Extractor")
    parser.add_argument(
        "--window", type=float, default=5.0,
        help="Sliding window size in seconds (default: 5.0)"
    )
    parser.add_argument(
        "--step", type=float, default=None,
        help="Window step/stride in seconds (default: window/2)"
    )
    args = parser.parse_args()
    step = args.step if args.step else args.window / 2.0
    main(window_sec=args.window, step_sec=step)
