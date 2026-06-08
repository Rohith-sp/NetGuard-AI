import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import joblib
import glob
from train_model import build_features_from_csv

DATA_DIR   = r"C:\IOT EL\NetGuard-AI\real_time_collector\collected_datasets"
list_of_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
CSV_PATH = max(list_of_files, key=os.path.getctime)
MODEL_OUT  = r"C:\IOT EL\NetGuard-AI\ml_model\netguard_model.pkl"

df = pd.read_csv(CSV_PATH)
feat_df = build_features_from_csv(df, window_sec=10.0)

FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
    "unique_modes",
]
X = feat_df[FEATURE_COLS]
y = feat_df["label"]

clf = joblib.load(MODEL_OUT)
y_pred = clf.predict(X)

# Confusion Matrix
cm = confusion_matrix(y, y_pred, labels=clf.classes_)
disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=clf.classes_)
fig, ax = plt.subplots(figsize=(10, 8))
disp.plot(ax=ax, cmap="Blues", xticks_rotation=45)
plt.title("NetGuard-AI 7-Class Confusion Matrix")
plt.tight_layout()
plt.savefig(r"C:\IOT EL\NetGuard-AI\ml_model\confusion_matrix.png", dpi=300)
plt.close()

# Feature Importance
importances = clf.feature_importances_
indices = np.argsort(importances)[::-1]
plt.figure(figsize=(10, 6))
sns.barplot(x=importances[indices], y=[FEATURE_COLS[i] for i in indices], palette="viridis")
plt.title("NetGuard-AI Feature Importance")
plt.xlabel("Importance Score")
plt.ylabel("Features")
plt.tight_layout()
plt.savefig(r"C:\IOT EL\NetGuard-AI\ml_model\feature_importance.png", dpi=300)
plt.close()

print("Plots generated successfully!")
