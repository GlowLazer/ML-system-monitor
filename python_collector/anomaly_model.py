import os
import sys
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# these are the exact columns the model trains and predicts on
# order matters, must match between train() and predict()
FEATURES = [
    "cpu_percent",
    "ram_used_gb",
    "disk_read_mbs",
    "disk_write_mbs",
    "gpu_util",
    "gpu_mem_gb",
    "net_in_mbs",
    "net_out_mbs",
]

MODEL_PATH  = "models/anomaly_model.pkl"
SCALER_PATH = "models/scaler.pkl"


# trains on a CSV of collected metrics and saves the model + scaler to disk
# contamination=0.05 means we expect about 5% of training samples to be anomalies
# StandardScaler is needed because Isolation Forest is sensitive to feature scale
def train(data_path="data/training_data.csv"):
    if not os.path.exists(data_path):
        print(f"Training data not found at {data_path}")
        print("Run main_loop.py --collect-only first to collect baseline data.")
        sys.exit(1)

    df = pd.read_csv(data_path)
    missing = [f for f in FEATURES if f not in df.columns]
    if missing:
        print(f"Missing columns in training data: {missing}")
        sys.exit(1)

    X = df[FEATURES].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
    )
    model.fit(X_scaled)

    os.makedirs("models", exist_ok=True)
    joblib.dump(model,  MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"Model trained on {len(df)} samples. Saved to {MODEL_PATH}")


# loads model and scaler from disk
# returns (model, scaler) or raises FileNotFoundError if not trained yet
def load():
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        raise FileNotFoundError("Model not found. Run: python3 anomaly_model.py --train")
    model  = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    return model, scaler


# takes a dict of current metric values and returns True if it looks like an anomaly
# Isolation Forest returns -1 for anomaly, 1 for normal
def predict(model, scaler, metrics: dict) -> bool:
    X = np.array([[metrics[f] for f in FEATURES]])
    X_scaled = scaler.transform(X)
    result = model.predict(X_scaled)
    return result[0] == -1


if __name__ == "__main__":
    if "--train" in sys.argv:
        train()
    else:
        print("Usage: python3 anomaly_model.py --train")
