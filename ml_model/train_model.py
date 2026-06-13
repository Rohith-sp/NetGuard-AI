"""
Retrains the NetGuard model using the new scale-invariant feature extraction
and upgrades the architecture to a Heterogeneous Ensemble (XGBoost + Random Forest + MLP).

Includes a wrapper class to maintain backward compatibility with the FastAPI backend.
"""
import os
import glob
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import VotingClassifier, RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
import joblib

# ── Relative Paths ────────────────────────────────────────────────────────────
import sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "real_time_collector", "collected_datasets"))
MODEL_OUT = os.path.join(SCRIPT_DIR, "netguard_model.pkl")

BACKEND_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "dashboard", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

from model_wrapper import EnsembleClassifierWrapper

# Helper functions
def safe_mean(v): return sum(v) / len(v) if v else 0.0
def safe_std(v):
    if len(v) < 2: return 0.0
    m = safe_mean(v)
    return np.std(v)

# ── Scale-invariant Feature Engineering ──────────────────────────────────────
def build_features_from_csv(df: pd.DataFrame, window_sec: float = 10.0) -> pd.DataFrame:
    """
    Group packets into 10-second sliding windows, group by device,
    and compute extreme scale-invariant values.
    """
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp_utc"]).astype("int64") / 1e9  # unix seconds

    # Exclude command and timesync control messages
    df_filtered = df[~df["topic"].isin(["netguard_rohit_77/cmd", "netguard_rohit_77/timesync"])].copy()
    df_filtered = df_filtered.sort_values("ts").reset_index(drop=True)

    rows = []
    step = 1.0  # stride (seconds)
    t_min = df_filtered["ts"].min()
    t_max = df_filtered["ts"].max()
    t = t_min + window_sec

    while t <= t_max + step:
        window = df_filtered[(df_filtered["ts"] >= t - window_sec) & (df_filtered["ts"] < t)]
        if len(window) < 1:
            t += step
            continue

        # Group window by device
        by_device = {}
        for _, r in window.iterrows():
            dev = r["device"]
            if not isinstance(dev, str):
                dev = str(r["topic"]).split("/")[-1]
            if dev not in by_device:
                by_device[dev] = []
            by_device[dev].append(r)

        device_counts = []
        device_rates = []
        device_mean_iats = []
        device_std_iats = []
        device_min_iats = []
        device_max_iats = []
        device_dup_ratios = []
        device_mean_seq_incs = []
        device_std_seq_incs = []
        device_unique_modes = []

        for dev, dev_pkts in by_device.items():
            dev_pkts = sorted(dev_pkts, key=lambda x: x["ts"])
            dn = len(dev_pkts)
            device_counts.append(dn)
            device_rates.append(dn / window_sec)

            # IATs
            if dn > 1:
                dev_iats = [(dev_pkts[i+1]["ts"] - dev_pkts[i]["ts"]) * 1000 for i in range(dn-1)]
            else:
                dev_iats = [window_sec * 1000]

            device_mean_iats.append(safe_mean(dev_iats))
            device_std_iats.append(safe_std(dev_iats))
            device_min_iats.append(min(dev_iats))
            device_max_iats.append(max(dev_iats))

            # Seqs
            dev_seqs = [int(p["seq"]) for p in dev_pkts if p["seq"] >= 0]
            if len(dev_seqs) > 1:
                dev_seq_incs = [dev_seqs[i+1] - dev_seqs[i] for i in range(len(dev_seqs)-1)]
            else:
                dev_seq_incs = [1]
            
            device_mean_seq_incs.append(safe_mean(dev_seq_incs))
            device_std_seq_incs.append(safe_std(dev_seq_incs))

            # Duplicate ratio
            seen, dups = set(), 0
            for s in dev_seqs:
                if s in seen: dups += 1
                seen.add(s)
            device_dup_ratios.append(dups / dn)

            # Modes
            device_unique_modes.append(len(set(p["mode"] for p in dev_pkts)))

        # Ground-truth label — majority vote within window
        label = window["label"].mode()[0]

        rows.append({
            "packet_count":          round(max(device_counts), 4),
            "packet_rate":           round(max(device_rates), 4),
            "mean_inter_arrival_ms": round(min(device_mean_iats), 2),
            "std_inter_arrival_ms":  round(max(device_std_iats), 2),
            "min_inter_arrival_ms":  round(min(device_min_iats), 2),
            "max_inter_arrival_ms":  round(min(device_max_iats), 2),
            "duplicate_ratio":       round(max(device_dup_ratios), 4),
            "seq_increment_mean":    round(min(device_mean_seq_incs), 4),
            "seq_increment_std":     round(max(device_std_seq_incs), 4),
            "unique_modes":          int(max(device_unique_modes)),
            "label":                 label,
        })
        t += step

    return pd.DataFrame(rows)

def main():
    print("\n==========================================================")
    print("   NETGUARD AI — MODEL ENSEMBLE TRAINING (Scale-Invariant) ")
    print("==========================================================\n")

    # 1. Load raw CSV
    list_of_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    if not list_of_files:
        raise FileNotFoundError("No CSV files found in " + DATA_DIR)
    csv_path = max(list_of_files, key=os.path.getctime)
    print(f"[*] Loading dataset: {os.path.basename(csv_path)}")
    df = pd.read_csv(csv_path)
    print(f"    Total raw packets: {len(df)}")

    # 2. Build windowed feature matrix
    print("[*] Building 10-second scale-invariant windowed features…")
    feat_df = build_features_from_csv(df, window_sec=10.0)
    print(f"    Windows generated: {len(feat_df)}")
    print("\n[*] Class distribution (windows):")
    print(feat_df["label"].value_counts().to_string())

    if len(feat_df) < 10:
        print("[ERROR] Not enough windows — check that the CSV path is correct.")
        return

    # 3. Target label encoding
    FEATURE_COLS = [
        "packet_count", "packet_rate",
        "mean_inter_arrival_ms", "std_inter_arrival_ms",
        "min_inter_arrival_ms",  "max_inter_arrival_ms",
        "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
        "unique_modes",
    ]
    X = feat_df[FEATURE_COLS]
    y = feat_df["label"]

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    print(f"\n[*] Splitting 80/20 (stratified)…")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
    )

    # 4. Define Base Classifiers
    rf = RandomForestClassifier(n_estimators=150, random_state=42, n_jobs=-1)
    mlp = MLPClassifier(hidden_layer_sizes=(100, 50), max_iter=1000, random_state=42)
    
    estimators = [('rf', rf), ('mlp', mlp)]

    # 5. Optional XGBoost addition
    try:
        from xgboost import XGBClassifier
        xgb = XGBClassifier(n_estimators=150, random_state=42, eval_metric='mlogloss')
        estimators.append(('xgb', xgb))
        print("[*] XGBoost successfully added to the Ensemble.")
    except ImportError:
        print("[WARN] xgboost not installed in active environment — training with RF + MLP only.")

    # 6. Fit Voting Ensemble
    print("[*] Training Soft-Voting Ensemble Classifier…")
    voting_clf = VotingClassifier(estimators=estimators, voting='soft')
    voting_clf.fit(X_train, y_train)

    # 7. Evaluate
    print("\n==========================================================")
    print("                 MODEL EVALUATION RESULTS                 ")
    print("==========================================================")
    y_pred = voting_clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n[+] Overall Accuracy: {acc * 100:.2f}%")
    print("\n[+] Classification Report:")
    print(classification_report(y_test, y_pred, target_names=le.classes_))

    # Feature importances from Random Forest
    rf_fitted = voting_clf.named_estimators_['rf']
    print("[+] Feature Importances (Random Forest fallback, top 5):")
    importances = sorted(zip(FEATURE_COLS, rf_fitted.feature_importances_), key=lambda x: -x[1])
    for feat, imp in importances[:5]:
        print(f"    {feat:<28} {imp*100:.1f}%")

    # Calculate feature baseline mean and std
    feature_means = {}
    feature_stds = {}
    for col in FEATURE_COLS:
        feature_means[col] = float(X[col].mean())
        feature_stds[col] = float(X[col].std())
        if feature_stds[col] == 0.0:
            feature_stds[col] = 1.0  # Avoid division by zero

    # 8. Save wrapped model
    wrapped_model = EnsembleClassifierWrapper(voting_clf, le, feature_means, feature_stds)
    joblib.dump(wrapped_model, MODEL_OUT)
    print(f"\n[SUCCESS] Scale-invariant Ensemble model saved to: {MODEL_OUT}")
    print(f"[INFO] Classes: {list(le.classes_)}\n")

if __name__ == "__main__":
    main()
