import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib
import shap

# ── Paths ───────────────────────────────────────────────────────────────────
DATA_DIR   = r"C:\IOT EL\NetGuard-AI\real_time_collector\collected_datasets"
MODEL_OUT  = r"C:\IOT EL\NetGuard-AI\ml_model\netguard_model.pkl"
PAPER_DIR  = r"C:\IOT EL"
ARTIFACTS_DIR = r"C:\Users\rohit\.gemini\antigravity-ide\brain\f18bd124-7c95-4063-913c-d4a797a4a12a"

# Load Latest CSV and Build Features
list_of_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
if not list_of_files:
    raise FileNotFoundError("No collected CSV datasets found.")

CSV_PATH = max(list_of_files, key=os.path.getctime)
df = pd.read_csv(CSV_PATH)

from train_model import build_features_from_csv
feat_df = build_features_from_csv(df, window_sec=10.0)

FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
    "unique_modes",
]

X = feat_df[FEATURE_COLS]
clf = joblib.load(MODEL_OUT)
y_pred = clf.predict(X)

print("Initializing SHAP explainer...")
explainer = shap.TreeExplainer(clf)
classes_list = list(clf.classes_)

new_plots = {
    "DATA_POISON": "shap_local_data_poison.png",
    "TOPIC_BOMB": "shap_local_topic_bomb.png",
    "EVASION_ATTACK": "shap_local_evasion_attack.png"
}

for cls_name, filename in new_plots.items():
    print(f"Generating SHAP plot for {cls_name}...")
    candidates = feat_df[(feat_df["label"] == cls_name) & (feat_df["label"] == y_pred)]
    if candidates.empty:
        candidates = feat_df[feat_df["label"] == cls_name]
        
    if candidates.empty:
        print(f"No samples found for {cls_name} in the latest dataset. Using synthetic baseline.")
        vals = np.zeros(len(FEATURE_COLS))
        raw_vals = np.zeros(len(FEATURE_COLS))
    else:
        idx = candidates.index[0]
        sample_x = X.loc[[idx]]
        raw_vals = sample_x.values[0]
        sv = explainer.shap_values(sample_x, check_additivity=False)
        
        cls_idx = classes_list.index(cls_name)
        if isinstance(sv, list):
            vals = sv[cls_idx][0]
        elif sv.ndim == 3:
            vals = sv[0, :, cls_idx]
        else:
            vals = sv[0]
            
    # Sort and plot
    sorted_idx = np.argsort(np.abs(vals))[::-1]
    sorted_features = [FEATURE_COLS[i] for i in sorted_idx]
    sorted_vals = vals[sorted_idx]
    sorted_raw = raw_vals[sorted_idx]
    
    plt.figure(figsize=(10, 5))
    colors = ['#f43f5e' if v >= 0 else '#3b82f6' for v in sorted_vals]
    labels = [f"{feat}\n(value = {r:.2f})" for feat, r in zip(sorted_features, sorted_raw)]
    
    bars = plt.barh(labels[::-1], sorted_vals[::-1], color=colors[::-1], edgecolor='none', height=0.6)
    plt.axvline(0, color='gray', linestyle='--', linewidth=0.8)
    plt.title(f"Local SHAP Attribution for {cls_name} Prediction", fontsize=12, fontweight='bold')
    plt.xlabel("SHAP Value (Feature Influence on Output Probability)")
    
    for bar in bars:
        width = bar.get_width()
        x_pos = width + 0.005 if width >= 0 else width - 0.035
        ha = 'left' if width >= 0 else 'right'
        plt.text(x_pos, bar.get_y() + bar.get_height()/2, f"{width:+.3f}", 
                 va='center', ha=ha, fontsize=8, fontweight='bold',
                 color='#475569')
                 
    plt.xlim(min(sorted_vals)*1.2 - 0.05, max(sorted_vals)*1.2 + 0.05)
    plt.tight_layout()
    
    # Save to both target locations
    plt.savefig(os.path.join(PAPER_DIR, filename), dpi=300)
    plt.savefig(os.path.join(ARTIFACTS_DIR, filename), dpi=300)
    plt.close()

print("New SHAP plots generated successfully!")
