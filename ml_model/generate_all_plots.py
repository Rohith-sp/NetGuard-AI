import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import joblib
import shap
from PIL import Image

# ── Paths ───────────────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(_DIR, "..", "real_time_collector", "collected_datasets")
MODEL_OUT  = os.path.join(_DIR, "netguard_model.pkl")
PAPER_DIR  = os.path.join(_DIR, "..", "paper_images")

os.makedirs(PAPER_DIR, exist_ok=True)

# ── Load Latest CSV and Build Features ───────────────────────────────────────
list_of_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
if not list_of_files:
    # If no files in collected_datasets, check for any training files in other locations
    raise FileNotFoundError("No collected CSV datasets found in real_time_collector/collected_datasets.")

CSV_PATH = max(list_of_files, key=os.path.getctime)
print(f"Using latest dataset: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)

from train_model import build_features_from_csv
feat_df = build_features_from_csv(df, window_sec=10.0)

FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
]

# Clean class labels to match the 7 classes
class_mapping = {
    'DATA_POISON': 'DATA_POISON',
    'DOS_FLOOD': 'DOS_FLOOD',
    'EVASION_ATTACK': 'EVASION_ATTACK',
    'NORMAL': 'NORMAL',
    'REPLAY_ATTACK': 'REPLAY_ATTACK',
    'SLOW_RATE_ATTACK': 'SLOW_RATE_ATTACK',
    'TOPIC_BOMB': 'TOPIC_BOMB'
}

X = feat_df[FEATURE_COLS]
y = feat_df["label"].map(class_mapping).fillna(feat_df["label"])

clf = joblib.load(MODEL_OUT)
y_pred = clf.predict(X)

# ── 1. Label Distribution Plot ───────────────────────────────────────────────
print("Generating label distribution plot...")
plt.figure(figsize=(9, 5))
# Harmonious custom palette matching NetGuard style
palette = sns.color_palette("viridis", len(y.unique()))
sns.countplot(y=y, order=y.value_counts().index, palette="viridis", hue=y, legend=False)
plt.title("NetGuard-AI Training Dataset Class Distribution", fontsize=12, fontweight='bold')
plt.xlabel("Sample Count")
plt.ylabel("Behavioral Classes")
plt.tight_layout()
plt.savefig(os.path.join(PAPER_DIR, "label_distribution.png"), dpi=300)
plt.close()

# ── 2. Confusion Matrix Plot ─────────────────────────────────────────────────
print("Generating confusion matrix...")
cm = confusion_matrix(y, y_pred, labels=clf.classes_)
fig, ax = plt.subplots(figsize=(10, 8))
disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=clf.classes_)
disp.plot(ax=ax, cmap="Blues", xticks_rotation=45)
plt.title("NetGuard-AI 7-Class Behavioral Confusion Matrix", fontsize=12, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(PAPER_DIR, "confusion_matrix.png"), dpi=300)
plt.close()

# ── 3. Global Feature Importance Plot ────────────────────────────────────────
print("Generating global feature importance plot...")
importances = clf.feature_importances_
indices = np.argsort(importances)[::-1]
plt.figure(figsize=(10, 6))
sns.barplot(x=importances[indices], y=[FEATURE_COLS[i] for i in indices], palette="mako", hue=[FEATURE_COLS[i] for i in indices], legend=False)
plt.title("NetGuard-AI Global Feature Importance (Random Forest Gini Impurity)", fontsize=12, fontweight='bold')
plt.xlabel("Importance Score")
plt.ylabel("Behavioral Features")
plt.tight_layout()
plt.savefig(os.path.join(PAPER_DIR, "global_feature_importance.png"), dpi=300)
plt.close()

# ── 4. SHAP Explanations ─────────────────────────────────────────────────────
print("Initializing SHAP TreeExplainer...")
explainer = shap.TreeExplainer(clf)

# Calculate SHAP values for a sample of the dataset to make it efficient
sample_size = min(200, len(X))
X_sample = X.sample(sample_size, random_state=42)
shap_values = explainer.shap_values(X_sample)

# Beeswarm summary plot
print("Generating SHAP beeswarm summary plot...")
plt.figure(figsize=(10, 6))
# For multiclass, explainer.shap_values returns a list of arrays (one for each class)
# We show the summary plot for the anomaly classification (aggregate contribution)
if isinstance(shap_values, list):
    # Take mean absolute SHAP values across classes or plot the primary target (e.g., DOS_FLOOD or REPLAY_ATTACK)
    # Standard SHAP summary plot on class 0 (e.g. Normal vs Attacks) or combine them
    shap.summary_plot(shap_values, X_sample, show=False)
else:
    shap.summary_plot(shap_values, X_sample, show=False)

plt.title("NetGuard-AI SHAP Feature Contribution Summary", fontsize=12, fontweight='bold')
plt.tight_layout()
temp_shap_path = os.path.join(PAPER_DIR, "shap_summary_beeswarm.png")
plt.savefig(temp_shap_path, dpi=300)
plt.close()

# Convert to JPEG as expected by the paper
im = Image.open(temp_shap_path)
im.convert("RGB").save(os.path.join(PAPER_DIR, "shap_summary_beeswarm.jpg"), "JPEG", quality=95)
os.remove(temp_shap_path)

# ── 5. Local SHAP Profiles ──────────────────────────────────────────────────
print("Generating local SHAP profiles...")

# Map of paper figures to class names
local_plots = {
    "NORMAL": "shap_local_normal.png",
    "DOS_FLOOD": "shap_local_dos_flood.png",
    "REPLAY_ATTACK": "shap_local_replay_attack.png",
    "SLOW_RATE_ATTACK": "shap_local_slow_rate_attack.png"
}

classes_list = list(clf.classes_)

for cls_name, filename in local_plots.items():
    # Find a representative index where ground truth matches predicted matches target class
    candidates = feat_df[(feat_df["label"] == cls_name) & (feat_df["label"] == y_pred)]
    if candidates.empty:
        # Fallback to any sample of that class
        candidates = feat_df[feat_df["label"] == cls_name]
    
    if candidates.empty:
        print(f"Warning: No samples found for class {cls_name}. Generating synthetic SHAP plot.")
        # Create a mock SHAP plot
        vals = np.zeros(len(FEATURE_COLS))
        raw_vals = np.zeros(len(FEATURE_COLS))
    else:
        idx = candidates.index[0]
        sample_x = X.loc[[idx]]
        raw_vals = sample_x.values[0]
        sv = explainer.shap_values(sample_x)
        
        # Get SHAP values for the specific class index
        cls_idx = classes_list.index(cls_name)
        if isinstance(sv, list):
            vals = sv[cls_idx][0]
        elif sv.ndim == 3:
            vals = sv[0, :, cls_idx]
        else:
            vals = sv[0]
            
    # Plot a horizontal bar chart of feature contributions
    sorted_idx = np.argsort(np.abs(vals))[::-1]
    sorted_features = [FEATURE_COLS[i] for i in sorted_idx]
    sorted_vals = vals[sorted_idx]
    sorted_raw = raw_vals[sorted_idx]
    
    plt.figure(figsize=(10, 5))
    colors = ['#f43f5e' if v >= 0 else '#3b82f6' for v in sorted_vals]
    
    # Format labels with raw values
    labels = [f"{feat}\n(value = {r:.2f})" for feat, r in zip(sorted_features, sorted_raw)]
    
    bars = plt.barh(labels[::-1], sorted_vals[::-1], color=colors[::-1], edgecolor='none', height=0.6)
    
    plt.axvline(0, color='gray', linestyle='--', linewidth=0.8)
    plt.title(f"Local SHAP Attribution for {cls_name} Prediction", fontsize=12, fontweight='bold')
    plt.xlabel("SHAP Value (Feature Influence on Output Probability)")
    
    # Add values on the bars
    for bar in bars:
        width = bar.get_width()
        x_pos = width + 0.005 if width >= 0 else width - 0.035
        ha = 'left' if width >= 0 else 'right'
        plt.text(x_pos, bar.get_y() + bar.get_height()/2, f"{width:+.3f}", 
                 va='center', ha=ha, fontsize=8, fontweight='bold',
                 color='#475569')
                 
    plt.xlim(min(sorted_vals)*1.2 - 0.05, max(sorted_vals)*1.2 + 0.05)
    plt.tight_layout()
    plt.savefig(os.path.join(PAPER_DIR, filename), dpi=300)
    plt.close()

print(f"All plots generated and saved in {PAPER_DIR} successfully!")
