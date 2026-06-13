import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib
import shap

# Paths
CSV_PATH = r"c:\Users\rohit\Documents\NetGuard-AI\real_time_collector\collected_datasets\telemetry_session_20260602_234537.csv"
MODEL_PATH = r"c:\Users\rohit\Documents\NetGuard-AI\ml_model\netguard_model.pkl"
ARTIFACT_DIR = r"C:\Users\rohit\.gemini\antigravity-ide\brain\9e8d0be9-38bc-4b34-93ec-5c611d0feef2"

os.makedirs(ARTIFACT_DIR, exist_ok=True)

# 1. Feature extraction
def build_features_from_csv(df: pd.DataFrame, window_sec: float = 10.0) -> pd.DataFrame:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp_utc"]).astype("int64") / 1e9
    atk = df[df["topic"] == "netguard_rohit_77/attacker"].copy()
    atk = atk.sort_values("ts").reset_index(drop=True)

    rows = []
    step = 5.0
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
            iats = [window_sec * 1000]

        seqs = [int(s) for s in window["seq"] if s >= 0]
        seq_incs = [seqs[i+1] - seqs[i] for i in range(len(seqs)-1)] if len(seqs) > 1 else [1]

        seen, dups = set(), 0
        for s in seqs:
            if s in seen: dups += 1
            seen.add(s)
        dup_ratio = dups / max(len(window), 1)

        n = len(window)
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

print("[*] Loading dataset...")
df = pd.read_csv(CSV_PATH)
df.loc[df["device"] != "esp32_3", "label"] = "NORMAL"

feat_df = build_features_from_csv(df)
FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
    "unique_modes",
]
X = feat_df[FEATURE_COLS]
y = feat_df["label"]

print("[*] Loading model...")
model = joblib.load(MODEL_PATH)
classes = list(model.classes_)

# Plot 1: Global Feature Importance
print("[*] Plotting Global Feature Importance...")
importances = model.feature_importances_
indices = np.argsort(importances)

plt.figure(figsize=(10, 6))
plt.title("NetGuard AI - Global Feature Importance (Random Forest)", fontsize=14, fontweight="bold", pad=15)
colors = plt.cm.viridis(np.linspace(0.3, 0.8, len(FEATURE_COLS)))
bars = plt.barh(range(len(FEATURE_COLS)), importances[indices], align="center", color=colors, edgecolor="grey", alpha=0.9)
plt.yticks(range(len(FEATURE_COLS)), [FEATURE_COLS[i].replace("_", " ") for i in indices], fontsize=11)
plt.xlabel("Relative Importance Score", fontsize=12, labelpad=10)

# Add grid and text labels
plt.grid(axis='x', linestyle='--', alpha=0.7)
for bar in bars:
    width = bar.get_width()
    plt.text(width + 0.005, bar.get_y() + bar.get_height()/2, f'{width*100:.2f}%', 
             va='center', ha='left', fontsize=10, fontweight='bold', color='#333333')

plt.xlim(0, max(importances) + 0.05)
plt.tight_layout()
global_plot_path = os.path.join(ARTIFACT_DIR, "global_feature_importance.png")
plt.savefig(global_plot_path, dpi=300)
plt.close()
print(f"[+] Saved global plot to {global_plot_path}")

# Plot 2: Local SHAP values
print("[*] Computing SHAP values...")
explainer = shap.TreeExplainer(model)
# Compute SHAP values for the whole dataset or a representative slice
shap_values = explainer.shap_values(X)

# We want to find a representative instance for DOS_FLOOD, REPLAY_ATTACK, SLOW_RATE_ATTACK
# Let's plot local SHAP explanations for these classes and save them as nice figures.
for target_class in ["DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "NORMAL"]:
    class_idx = classes.index(target_class)
    # Find indices of instances of this class where the model got it right and had high probability
    pred_probs = model.predict_proba(X)
    pred_labels = model.predict(X)
    
    class_indices = np.where((y == target_class) & (pred_labels == target_class))[0]
    if len(class_indices) == 0:
        continue
    
    # Sort by probability of the target class to find the most representative one
    best_idx = class_indices[np.argmax(pred_probs[class_indices, class_idx])]
    
    # Get values
    # In tree explainer with multi-class, shap_values is a list of arrays (one per class), or a 3D array (samples, features, classes)
    # Let's see the structure of shap_values
    if isinstance(shap_values, list):
        inst_shap = shap_values[class_idx][best_idx]
    else:
        # Array shape might be (samples, features, classes)
        if len(shap_values.shape) == 3:
            inst_shap = shap_values[best_idx, :, class_idx]
        else:
            inst_shap = shap_values[best_idx]
            
    inst_features = X.iloc[best_idx]
    
    # Plot custom matplotlib waterfall-like bar chart for this instance
    plt.figure(figsize=(10, 5.5))
    
    # Sort features by absolute SHAP value
    sorted_indices = np.argsort(np.abs(inst_shap))
    
    y_pos = np.arange(len(FEATURE_COLS))
    colors_shap = ['#e53e3e' if inst_shap[idx] > 0 else '#319795' for idx in sorted_indices]
    
    plt.title(f"SHAP Local Explanation: Predicted Class = {target_class}\n(Model Confidence: {pred_probs[best_idx, class_idx]*100:.1f}%)", 
              fontsize=13, fontweight="bold", pad=15)
    
    bars = plt.barh(y_pos, inst_shap[sorted_indices], color=colors_shap, edgecolor="grey", alpha=0.9)
    plt.yticks(y_pos, [f"{FEATURE_COLS[idx].replace('_', ' ')} = {inst_features.iloc[idx]}" for idx in sorted_indices], fontsize=10)
    plt.xlabel("SHAP Value (Contribution to anomaly score)", fontsize=11, labelpad=10)
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    
    # Draw a vertical line at 0
    plt.axvline(0, color='black', linewidth=0.8, linestyle='-')
    
    # Add labels to bars
    for bar in bars:
        w = bar.get_width()
        x_coord = w + 0.01 if w >= 0 else w - 0.01
        align = 'left' if w >= 0 else 'right'
        plt.text(x_coord, bar.get_y() + bar.get_height()/2, f'{w:+.3f}', 
                 va='center', ha=align, fontsize=9, fontweight='bold')
                 
    # Adjust x limits to fit labels
    current_xlim = plt.xlim()
    padding = (current_xlim[1] - current_xlim[0]) * 0.1
    plt.xlim(current_xlim[0] - padding, current_xlim[1] + padding)
    
    plt.tight_layout()
    local_plot_path = os.path.join(ARTIFACT_DIR, f"shap_local_{target_class.lower()}.png")
    plt.savefig(local_plot_path, dpi=300)
    plt.close()
    print(f"[+] Saved local plot for {target_class} to {local_plot_path}")

print("[*] Generating general summary SHAP plot...")
plt.figure(figsize=(10, 6))
# For summary plot, we need to pass the list/array appropriately.
# TreeExplainer summary_plot supports multi-class or single-class.
# Let's plot the summary for Class 1 (or the target classes)
if isinstance(shap_values, list):
    # shap_values[class_idx]
    # Let's use class_idx for the main attack classes
    shap.summary_plot(shap_values, X, show=False, class_names=classes)
else:
    shap.summary_plot(shap_values, X, show=False)
plt.title("SHAP Beeswarm Summary Plot (Global Interaction)", fontsize=14, fontweight="bold", pad=15)
plt.tight_layout()
summary_plot_path = os.path.join(ARTIFACT_DIR, "shap_summary_beeswarm.png")
plt.savefig(summary_plot_path, dpi=300)
plt.close()
print(f"[+] Saved SHAP summary beeswarm plot to {summary_plot_path}")

print("[SUCCESS] All plots generated successfully!")
