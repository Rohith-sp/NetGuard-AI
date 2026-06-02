"""
NetGuard AI — Telemetry Feature Extractor for Real-time Sessions
================================================================
Reads a raw telemetry CSV session produced by real_time_collector.py and 
applies a sliding time-window per device to compute aggregated network-behavior features.

The resulting features CSV is formatted exactly for Random Forest model inputs.

Usage:
  python extractor.py --file collected_datasets/telemetry_session_2026xxxx.csv
  python extractor.py  # Autodetects the latest session CSV in collected_datasets
"""

import argparse
import csv
import os
import sys
import glob
import math
from collections import defaultdict
from datetime import datetime, timezone

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

def parse_ts(ts_str: str) -> float:
    """Parse ISO-8601 UTC timestamp -> float epoch seconds."""
    ts_str = ts_str.rstrip("Z")
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

def compute_features(packets: list, window_start: float, window_end: float, device: str) -> dict:
    n = len(packets)
    duration = window_end - window_start

    # Inter-arrival times
    timestamps = sorted(p["_epoch"] for p in packets)
    inter_arrivals = [
        (timestamps[i+1] - timestamps[i]) * 1000.0
        for i in range(len(timestamps) - 1)
    ]

    # Sequence analysis
    seqs = [p["seq"] for p in packets if p["seq"] != -1]
    seq_increments = [seqs[i+1] - seqs[i] for i in range(len(seqs) - 1)]

    seen_seqs = set()
    duplicate_count = 0
    for s in seqs:
        if s in seen_seqs:
            duplicate_count += 1
        seen_seqs.add(s)
    duplicate_ratio = duplicate_count / n if n > 0 else 0.0

    modes = [p["mode"] for p in packets]
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

def main(input_file: str, window_sec: float, step_sec: float):
    # If no file is provided, auto-detect the newest session CSV in collected_datasets
    if not input_file:
        datasets_dir = os.path.join(os.path.dirname(__file__), "collected_datasets")
        if not os.path.exists(datasets_dir):
            print(f"[!] Directory not found: {datasets_dir}")
            print("    Please run real_time_collector.py first to collect some data.")
            sys.exit(1)
            
        csv_files = glob.glob(os.path.join(datasets_dir, "telemetry_session_*.csv"))
        if not csv_files:
            print("[!] No telemetry_session_*.csv files found in collected_datasets.")
            sys.exit(1)
            
        # Get newest file based on modification time
        input_file = max(csv_files, key=os.path.getmtime)
        print(f"[*] Auto-detected newest session file: {os.path.basename(input_file)}")

    if not os.path.exists(input_file):
        print(f"[!] Target file does not exist: {input_file}")
        sys.exit(1)

    # Output path in same directory with "features_" prefix
    dir_name = os.path.dirname(input_file)
    base_name = os.path.basename(input_file)
    output_file = os.path.join(dir_name, "features_" + base_name)

    print("=" * 70)
    print("  NetGuard AI — Real-time Feature Extractor")
    print(f"  Input  : {input_file}")
    print(f"  Output : {output_file}")
    print(f"  Window : {window_sec}s  |  Step : {step_sec}s")
    print("=" * 70)

    # 1. Load telemetry CSV
    device_packets = defaultdict(list)
    total_packets = 0

    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_packets += 1
            epoch = parse_ts(row["timestamp_utc"])
            pkt = {
                "_epoch": epoch,
                "topic": row["topic"],
                "mode": row["mode"],
                "label": row["label"],
                "seq": int(row["seq"]) if row["seq"] not in ("", "-1") else -1
            }
            device = row["device"]
            device_packets[device].append(pkt)

    print(f"[+] Loaded {total_packets} packets across {len(device_packets)} device channels.")

    # 2. Slide window per device
    all_features = []

    for device, packets in device_packets.items():
        if len(packets) < 2:
            print(f"    {device:<14} → Skipped (insufficient packets)")
            continue

        packets.sort(key=lambda p: p["_epoch"])
        t_start = packets[0]["_epoch"]
        t_end = packets[-1]["_epoch"]

        win_start = t_start
        windows_processed = 0

        while win_start + window_sec <= t_end + step_sec:
            win_end = win_start + window_sec

            # Gather packets in window [win_start, win_end)
            window_pkts = [p for p in packets if win_start <= p["_epoch"] < win_end]

            # We need at least 2 packets in a window to calculate meaningful inter-arrival statistics
            if len(window_pkts) >= 2:
                feat = compute_features(window_pkts, win_start, win_end, device)
                all_features.append(feat)
                windows_processed += 1

            win_start += step_sec

        print(f"    {device:<14} → {windows_processed} feature windows extracted")

    if not all_features:
        print("\n[!] No windows met feature calculation criteria (minimum 2 packets per window).")
        print("    Try adjusting window size or collecting more data.")
        sys.exit(1)

    # 3. Write features CSV
    all_features.sort(key=lambda r: r["window_start_utc"])
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLS)
        writer.writeheader()
        writer.writerows(all_features)

    print(f"\n[+] Processing complete! {len(all_features)} windows written to:")
    print(f"    {output_file}")

    # Display label summary
    labels = defaultdict(int)
    for row in all_features:
        labels[row["label"]] += 1

    print("\n    Class Distribution:")
    for lbl, count in sorted(labels.items()):
        percentage = 100.0 * count / len(all_features)
        print(f"      {lbl:<22} : {count:>4} windows ({percentage:.1f}%)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetGuard Sliding-Window Feature Extractor")
    parser.add_argument("--file", type=str, default="", help="Path to telemetry session CSV")
    parser.add_argument("--window", type=float, default=5.0, help="Sliding window size in seconds (default: 5s)")
    parser.add_argument("--step", type=float, default=None, help="Step increment size (default: window/2)")
    
    args = parser.parse_args()
    step_size = args.step if args.step else args.window / 2.0
    main(args.file, args.window, step_size)
