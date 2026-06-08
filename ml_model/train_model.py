"""
Retrains the NetGuard Random Forest model using the same 10-feature schema
that the FastAPI backend (main.py) uses for live inference.

Features match extract_features() in backend/main.py exactly.
"""
import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import joblib

# ── Paths ─────────────────────────────────────────────────────────────────────
import glob
DATA_DIR   = r"C:\IOT EL\NetGuard-AI\real_time_collector\collected_datasets"
list_of_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
if not list_of_files:
    raise FileNotFoundError("No CSV files found in " + DATA_DIR)
CSV_PATH = max(list_of_files, key=os.path.getctime)
MODEL_OUT  = r"C:\IOT EL\NetGuard-AI\ml_model\netguard_model.pkl"

# ── Feature engineering — mirrors backend extract_features() exactly ──────────
def build_features_from_csv(df: pd.DataFrame, window_sec: float = 10.0) -> pd.DataFrame:
    """
    Group packets into 10-second sliding windows per device, then compute
    the same 10 features the backend extracts live from the packet_buffer.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp_utc"]).astype("int64") / 1e9  # unix seconds

    # Only use attacker node or explicitly labeled attack packets that might spoof/broadcast
    atk = df[(df["topic"] == "netguard/attacker") | (df["label"] == "DATA_POISON") | (df["label"] == "TOPIC_BOMB")].copy()
    atk = atk.sort_values("ts").reset_index(drop=True)

    rows = []
    step = 1.0  # stride (seconds)
    t_min = atk["ts"].min()
    t_max = atk["ts"].max()
    t = t_min + window_sec

    while t <= t_max + step:
        window = atk[(atk["ts"] >= t - window_sec) & (atk["ts"] < t)]
        if len(window) < 1:
            t += step
            continue

        timestamps = sorted(window["ts"].tolist())
        if len(timestamps) > 1:
            iats = [(timestamps[i+1] - timestamps[i]) * 1000 for i in range(len(timestamps)-1)]
        else:
            iats = [window_sec * 1000]  # single-packet window = huge IAT (slow rate signature)

        seqs = [int(s) for s in window["seq"] if s >= 0]
        seq_incs = [seqs[i+1] - seqs[i] for i in range(len(seqs)-1)] if len(seqs) > 1 else [1]

        seen, dups = set(), 0
        for s in seqs:
            if s in seen: dups += 1
            seen.add(s)
        dup_ratio = dups / max(len(window), 1)

        n = len(window)

        # Ground-truth label — majority vote within window
        label = window["label"].mode()[0]

        rows.append({
            "packet_count":          n,
            "packet_rate":           round(n / window_sec, 4),
            "mean_inter_arrival_ms": round(np.mean(iats), 2),
            "std_inter_arrival_ms":  round(np.std(iats), 2) if len(iats) > 1 else 0.0,
            "min_inter_arrival_ms":  round(min(iats), 2),
            "max_inter_arrival_ms":  round(max(iats), 2),
            "duplicate_ratio":       round(dup_ratio, 4),
            "seq_increment_mean":    round(np.mean(seq_incs), 4),
            "seq_increment_std":     round(np.std(seq_incs), 4) if len(seq_incs) > 1 else 0.0,
            "unique_modes":          int(window["mode"].nunique()),
            "label":                 label,
        })
        t += step

    return pd.DataFrame(rows)


def main():
    print("\n==========================================================")
    print("   NETGUARD AI — MODEL RETRAINING (10-Feature Schema)   ")
    print("==========================================================\n")

    # 1. Load raw CSV
    print(f"[*] Loading dataset: {os.path.basename(CSV_PATH)}")
    df = pd.read_csv(CSV_PATH)
    print(f"    Total raw packets: {len(df)}")

    # 2. (Removed label filtering to preserve ALL attack classes based on ground truth)

    # 3. Build windowed feature matrix
    print("[*] Building 10-second windowed feature vectors…")
    feat_df = build_features_from_csv(df, window_sec=10.0)
    print(f"    Windows generated: {len(feat_df)}")
    print("\n[*] Class distribution (windows):")
    print(feat_df["label"].value_counts().to_string())

    if len(feat_df) < 10:
        print("[ERROR] Not enough windows — check that the CSV path is correct.")
        return

    # 4. Train/test split
    FEATURE_COLS = [
        "packet_count", "packet_rate",
        "mean_inter_arrival_ms", "std_inter_arrival_ms",
        "min_inter_arrival_ms",  "max_inter_arrival_ms",
        "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
        "unique_modes",
    ]
    X = feat_df[FEATURE_COLS]
    y = feat_df["label"]

    print(f"\n[*] Splitting 80/20 (stratified)…")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 5. Train
    print("[*] Training Random Forest (200 trees)…")
    clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1, max_depth=None)
    clf.fit(X_train, y_train)

    # 6. Evaluate
    print("\n==========================================================")
    print("                 MODEL EVALUATION RESULTS                 ")
    print("==========================================================")
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n[+] Overall Accuracy: {acc * 100:.2f}%")
    print("\n[+] Classification Report:")
    print(classification_report(y_test, y_pred))

    # Feature importances
    print("[+] Feature Importances (top 5):")
    importances = sorted(zip(FEATURE_COLS, clf.feature_importances_), key=lambda x: -x[1])
    for feat, imp in importances[:5]:
        print(f"    {feat:<28} {imp*100:.1f}%")

    # 7. Save
    joblib.dump(clf, MODEL_OUT)
    print(f"\n[SUCCESS] Model saved to: {MODEL_OUT}")
    print(f"[INFO] Classes: {list(clf.classes_)}")
    print(f"[INFO] This model is now compatible with the dashboard backend.\n")


if __name__ == "__main__":
    main()
