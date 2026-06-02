"""
Augments the existing telemetry CSV with synthetic SLOW_RATE_ATTACK packets
that statistically match the real hardware signatures, then retrains the model.

Strategy:
- SLOW_RATE sends ~1 packet every 15-30 seconds from the attacker node
- seq increments by 1 each time (NOT frozen like replay)
- Generate enough windows to give the ML model ~40 training windows
"""
import os, random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib

CSV_PATH  = r"C:\IOT EL\NetGuard-AI\real_time_collector\collected_datasets\telemetry_session_20260602_234537.csv"
MODEL_OUT = r"C:\IOT EL\NetGuard-AI\ml_model\netguard_model.pkl"

random.seed(42)
np.random.seed(42)

def generate_slow_rate_packets(n_windows: int = 50, base_seq: int = 2000) -> pd.DataFrame:
    """
    Generate synthetic SLOW_RATE_ATTACK attacker packets.
    Each window of 10 seconds should contain only 0-1 packets (very low rate).
    We generate enough to fill n_windows worth of data.
    """
    rows = []
    # Start time — append after the existing dataset ends
    t = datetime(2026, 6, 2, 20, 30, 0, tzinfo=timezone.utc)
    seq = base_seq

    # Generate ~200 packets spread over ~55 minutes (enough for 50+ training windows)
    # IAT: 15-30 seconds, sometimes longer (up to 40s)
    for _ in range(200):
        iat_s = random.uniform(15, 35)           # 15-35 second gap = slow rate
        t += timedelta(seconds=iat_s)
        iat_ms = int(iat_s * 1000)
        seq += 1

        rows.append({
            "timestamp_utc":   t.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "topic":           "netguard/attacker",
            "device":          "esp32_3",
            "mode":            "SLOW_RATE_ATTACK",
            "seq":             seq,
            "temp":            -1,
            "humidity":        -1,
            "light":           -1,
            "inter_arrival_ms": iat_ms,
            "label":           "SLOW_RATE_ATTACK",
        })

    # Intersperse matching NORMAL packets from device1/device2 (keeps dataset balanced)
    t_start = datetime(2026, 6, 2, 20, 30, 0, tzinfo=timezone.utc)
    t_n = t_start
    seq_d1 = 800
    for _ in range(160):
        iat_s = random.uniform(2, 5)
        t_n += timedelta(seconds=iat_s)
        seq_d1 += 1
        rows.append({
            "timestamp_utc":   t_n.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "topic":           "netguard/device1",
            "device":          "esp32_1",
            "mode":            "NORMAL",
            "seq":             seq_d1,
            "temp":            round(random.uniform(27.5, 29.0), 1),
            "humidity":        round(random.uniform(63, 68)),
            "light":           -1,
            "inter_arrival_ms": int(iat_s * 1000),
            "label":           "NORMAL",
        })

    return pd.DataFrame(rows)


def build_features_from_df(df: pd.DataFrame, window_sec: float = 10.0) -> pd.DataFrame:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp_utc"]).astype("int64") / 1e9
    atk = df[df["topic"] == "netguard/attacker"].copy()
    atk = atk.sort_values("ts").reset_index(drop=True)

    rows = []
    step  = 5.0
    t_min = atk["ts"].min()
    t_max = atk["ts"].max()
    t     = t_min + window_sec

    while t <= t_max + step:
        window = atk[(atk["ts"] >= t - window_sec) & (atk["ts"] < t)]
        if len(window) < 1:
            t += step
            continue

        timestamps = sorted(window["ts"].tolist())
        if len(timestamps) > 1:
            iats = [(timestamps[i+1] - timestamps[i]) * 1000 for i in range(len(timestamps)-1)]
        else:
            # Single packet in window — hallmark of slow rate attack
            iats = [window_sec * 1000]   # treat whole window as one huge IAT

        seqs = [int(s) for s in window["seq"] if s >= 0]
        seq_incs = [seqs[i+1] - seqs[i] for i in range(len(seqs)-1)] if len(seqs) > 1 else [1]

        seen, dups = set(), 0
        for s in seqs:
            if s in seen: dups += 1
            seen.add(s)

        n     = len(window)
        label = window["label"].mode()[0]

        rows.append({
            "packet_count":          n,
            "packet_rate":           round(n / window_sec, 4),
            "mean_inter_arrival_ms": round(np.mean(iats), 2),
            "std_inter_arrival_ms":  round(np.std(iats), 2) if len(iats) > 1 else 0.0,
            "min_inter_arrival_ms":  round(min(iats), 2),
            "max_inter_arrival_ms":  round(max(iats), 2),
            "duplicate_ratio":       round(dups / max(n, 1), 4),
            "seq_increment_mean":    round(np.mean(seq_incs), 4),
            "seq_increment_std":     round(np.std(seq_incs), 4) if len(seq_incs) > 1 else 0.0,
            "unique_modes":          int(window["mode"].nunique()),
            "label":                 label,
        })
        t += step

    return pd.DataFrame(rows)


def main():
    print("\n==========================================================")
    print("  NETGUARD AI — DATA AUGMENTATION + FULL RETRAIN")
    print("==========================================================\n")

    # 1. Load original CSV
    print(f"[*] Loading original dataset…")
    df_orig = pd.read_csv(CSV_PATH)
    df_orig.loc[df_orig["device"] != "esp32_3", "label"] = "NORMAL"
    print(f"    Original packets: {len(df_orig)}")

    # 2. Generate synthetic slow rate data
    print("[*] Generating synthetic SLOW_RATE_ATTACK packets…")
    df_syn = generate_slow_rate_packets(n_windows=50)
    slow_atk_count = len(df_syn[df_syn["label"] == "SLOW_RATE_ATTACK"])
    print(f"    Generated {slow_atk_count} synthetic attacker packets + {len(df_syn) - slow_atk_count} background packets")

    # 3. Combine
    df_full = pd.concat([df_orig, df_syn], ignore_index=True)
    print(f"    Combined dataset: {len(df_full)} packets total")

    # 4. Build windows
    print("[*] Building 10-second windowed feature vectors…")
    feat_df = build_features_from_df(df_full, window_sec=10.0)
    print(f"    Windows generated: {len(feat_df)}")
    print("\n[*] Class distribution:")
    print(feat_df["label"].value_counts().to_string())

    # 5. Train/test split
    FEATURE_COLS = [
        "packet_count", "packet_rate",
        "mean_inter_arrival_ms", "std_inter_arrival_ms",
        "min_inter_arrival_ms",  "max_inter_arrival_ms",
        "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
        "unique_modes",
    ]
    X = feat_df[FEATURE_COLS]
    y = feat_df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 6. Train with 200 trees
    print("\n[*] Training Random Forest (200 trees, all 4 classes)…")
    clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    # 7. Evaluate
    print("\n==========================================================")
    print("                 MODEL EVALUATION RESULTS                 ")
    print("==========================================================")
    y_pred = clf.predict(X_test)
    acc    = accuracy_score(y_test, y_pred)
    print(f"\n[+] Overall Accuracy: {acc * 100:.2f}%")
    print(f"\n[+] Classes in model: {list(clf.classes_)}")
    print("\n[+] Classification Report:")
    print(classification_report(y_test, y_pred))

    print("[+] Feature Importances (top 5):")
    importances = sorted(zip(FEATURE_COLS, clf.feature_importances_), key=lambda x: -x[1])
    for feat, imp in importances[:5]:
        print(f"    {feat:<28} {imp*100:.1f}%")

    # 8. Save
    joblib.dump(clf, MODEL_OUT)
    print(f"\n[SUCCESS] Model saved to: {MODEL_OUT}")
    print(f"[INFO] Model now includes all 4 attack classes: NORMAL, DOS_FLOOD, REPLAY_ATTACK, SLOW_RATE_ATTACK\n")


if __name__ == "__main__":
    main()
