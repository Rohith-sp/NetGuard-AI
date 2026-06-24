import joblib
import numpy as np

MODEL_PATH = r"C:\IOT EL\NetGuard-AI\ml_model\netguard_model.pkl"
model = joblib.load(MODEL_PATH)

print("Classes:", model.classes_)

# Let's define FEATURE_COLS:
FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
    "unique_modes",
]

# Case 1: Normal flow (attacker node in NORMAL mode)
# Attacker publishes every 2-5s, so over 10s: count ~3, rate ~0.3, iat ~3500ms
normal_features = [
    3,    # packet_count
    0.3,  # packet_rate
    3500.0, # mean_inter_arrival_ms
    500.0,  # std_inter_arrival_ms
    3000.0, # min_inter_arrival_ms
    4000.0, # max_inter_arrival_ms
    0.0,  # duplicate_ratio
    1.0,  # seq_increment_mean
    0.0,  # seq_increment_std
    1     # unique_modes (only "NORMAL")
]

X = np.array([normal_features])
pred = model.predict(X)[0]
probs = model.predict_proba(X)[0]
print("\n--- Test with Typical Normal Features ---")
for cls, prob in zip(model.classes_, probs):
    print(f"{cls:<20}: {prob*100:.2f}%")
print(f"Prediction: {pred}")

# Let's inspect feature importances:
print("\n--- Feature Importances ---")
for feat, imp in zip(FEATURE_COLS, model.feature_importances_):
    print(f"{feat:<25}: {imp*100:.2f}%")
