"""Pipeline inference module for complex-sim-platform.

Loads trained model weights from JSON checkpoints and performs
inference on new data using numpy operations.
"""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np


@dataclass
class InferenceConfig:
    """Configuration for the inference engine."""
    batch_size: int = 256
    confidence_threshold: float = 0.5
    output_proba: bool = True
    use_gpu_fallback: bool = False


class ModelInferencer:
    """Loads model weights and performs inference on new data."""

    def __init__(self, config: Optional[InferenceConfig] = None):
        self.config = config or InferenceConfig()
        self.model = None
        self._loaded = False

    def load(self, checkpoint_path: str) -> bool:
        """Load model weights from a JSON checkpoint file.

        Args:
            checkpoint_path: Path to the JSON checkpoint file.

        Returns:
            True if loading succeeded.
        """
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        with open(checkpoint_path, "r") as fh:
            data = json.load(fh)

        weights = [np.array(w) for w in data["weights"]]
        biases = [np.array(b) for b in data["biases"]]

        self.model = {
            "weights": weights,
            "biases": biases,
            "layers": [w.shape[0] for w in weights] + [weights[-1].shape[1]],
            "config": data.get("config", {}),
        }
        self._loaded = True
        return True

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Run inference on a feature matrix.

        Args:
            X: Feature matrix of shape (n_samples, n_features).

        Returns:
            Predictions array of shape (n_samples,).
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Forward pass through all layers
        activation = X.astype(np.float64)
        for i, (w, b) in enumerate(zip(self.model["weights"], self.model["biases"])):
            z = activation @ w + b
            if i < len(self.model["weights"]) - 1:
                # ReLU activation for hidden layers
                activation = np.maximum(0, z)
            else:
                activation = z  # Linear output for final layer

        return activation.flatten()

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return prediction probabilities (for classification).

        Applies sigmoid to output if single output, softmax if multiple.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded.")

        output = self.predict(X)
        if output.ndim == 0 or len(output) == 1:
            return 1.0 / (1.0 + np.exp(-output))
        # Softmax for multi-class
        exp_out = np.exp(output - np.max(output))
        return exp_out / np.sum(exp_out)

    def predict_batch(
        self, X: np.ndarray, batch_size: Optional[int] = None
    ) -> np.ndarray:
        """Run inference on large arrays in batches."""
        batch_size = batch_size or self.config.batch_size
        results = []
        for i in range(0, len(X), batch_size):
            batch = X[i:i + batch_size]
            results.append(self.predict(batch))
        return np.concatenate(results)

    def predict_with_confidence(self, X: np.ndarray) -> List[Dict[str, Any]]:
        """Return predictions with confidence scores."""
        predictions = self.predict(X)
        if self.config.output_proba:
            proba = self.predict_proba(X)
        else:
            proba = np.abs(predictions)

        results = []
        for i in range(len(X)):
            confidence = float(proba[i]) if np.isscalar(proba[i]) else float(np.max(proba[i]))
            results.append({
                "prediction": float(predictions[i]),
                "confidence": confidence,
                "above_threshold": confidence >= self.config.confidence_threshold,
            })
        return results

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """Evaluate model performance on labeled data."""
        predictions = self.predict(X)
        mse = float(np.mean((predictions - y) ** 2))
        mae = float(np.mean(np.abs(predictions - y)))
        rmse = float(np.sqrt(mse))
        r2 = 1.0 - (np.sum((y - predictions) ** 2) / np.sum((y - np.mean(y)) ** 2))

        # Max absolute error
        max_error = float(np.max(np.abs(predictions - y)))

        # Mean relative error
        nonzero = np.abs(y) > 1e-10
        mre = float(np.mean(np.abs((predictions[nonzero] - y[nonzero]) / y[nonzero]))) if np.any(nonzero) else 0.0

        return {
            "mse": mse,
            "rmse": rmse,
            "mae": mae,
            "r2_score": float(r2),
            "max_error": max_error,
            "mean_relative_error": mre,
            "n_samples": len(X),
            "mean_prediction": float(np.mean(predictions)),
            "std_prediction": float(np.std(predictions)),
        }

    def export_predictions(
        self, X: np.ndarray, filepath: str, records: Optional[List[Dict]] = None
    ) -> str:
        """Export predictions to JSON file."""
        predictions = self.predict_with_confidence(X)
        output = []
        for i, pred in enumerate(predictions):
            entry = pred
            if records and i < len(records):
                entry["_original"] = {k: v for k, v in records[i].items() if not k.startswith("_")}
            output.append(entry)

        with open(filepath, "w") as fh:
            json.dump(output, fh, indent=2)
        return filepath

    def feature_importance(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Compute simple feature importance via weight magnitude.

        Approximates feature importance using the first layer weights.
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded.")
        first_layer_weights = self.model["weights"][0]
        # Sum absolute weights per input feature
        importance = np.sum(np.abs(first_layer_weights), axis=1)
        return importance / np.sum(importance) if np.sum(importance) > 0 else importance


def infer(
    checkpoint_path: str,
    X: np.ndarray,
    config: Optional[InferenceConfig] = None,
) -> Dict[str, Any]:
    """Convenience function to load a checkpoint and run inference."""
    inferencer = ModelInferencer(config)
    inferencer.load(checkpoint_path)
    predictions = inferencer.predict(X)
    metrics = inferencer.evaluate(X, np.zeros(len(X)))  # Placeholder - pass real y if available
    return {
        "predictions": predictions.tolist(),
        "n_samples": len(X),
        "model_config": inferencer.model.get("config", {}),
    }
