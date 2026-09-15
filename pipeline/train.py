"""Pipeline training module for complex-sim-platform.

Uses simcore.neural to train models on collected data.
Provides utilities for data preparation, training loops, and
checkpoint management.
"""

import json
import os
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field as dc_field

import numpy as np

# Attempt to import from simcore.neural if available
try:
    from simcore.neural import NeuralNetwork, AdamOptimizer
    SIMCORE_AVAILABLE = True
except ImportError:
    SIMCORE_AVAILABLE = False


@dataclass
class TrainingConfig:
    """Configuration for the training pipeline."""
    epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 0.001
    hidden_layers: Tuple[int, ...] = (64, 32, 16)
    activation: str = "relu"
    output_activation: str = "linear"
    loss_fn: str = "mse"
    optimizer: str = "adam"
    dropout_rate: float = 0.1
    early_stopping_patience: int = 10
    validation_split: float = 0.2
    checkpoint_dir: str = "./checkpoints"
    seed: int = 42
    verbose: bool = True


class DataPreparer:
    """Prepares collected data for training."""

    def __init__(self, config: Optional[TrainingConfig] = None):
        self.config = config or TrainingConfig()
        self._rng = np.random.default_rng(self.config.seed)

    def prepare_from_records(
        self, records: List[Dict[str, Any]],
        feature_fields: List[str],
        target_field: str,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Convert record list to feature matrix and target vector."""
        features = []
        targets = []
        for rec in records:
            feat = [float(rec.get(f, 0)) for f in feature_fields]
            target = float(rec.get(target_field, 0))
            features.append(feat)
            targets.append(target)
        return np.array(features, dtype=np.float64), np.array(targets, dtype=np.float64)

    def train_test_split(
        self, X: np.ndarray, y: np.ndarray, test_size: float = 0.2
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Split data into training and validation sets."""
        n = len(X)
        indices = self._rng.permutation(n)
        split = int(n * (1 - test_size))
        train_idx, val_idx = indices[:split], indices[split:]
        return X[train_idx], X[val_idx], y[train_idx], y[val_idx]

    def normalize_features(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Z-score normalize features. Returns (normalized, mean, std)."""
        mean = np.mean(X, axis=0)
        std = np.std(X, axis=0)
        std = np.where(std == 0, 1.0, std)
        return (X - mean) / std, mean, std


class PipelineTrainer:
    """Trains neural network models on collected pipeline data."""

    def __init__(self, config: Optional[TrainingConfig] = None):
        self.config = config or TrainingConfig()
        self._preparer = DataPreparer(config)
        self.history: Dict[str, List[float]] = {}
        self.model = None
        self._rng = np.random.default_rng(config.seed)

    def build_model(self, input_dim: int) -> Any:
        """Build the neural network model.

        If simcore.neural is available, use it. Otherwise,
        create a numpy-based MLP implementation."""
        if SIMCORE_AVAILABLE:
            self.model = NeuralNetwork(
                layers=list(self.config.hidden_layers),
                activation=self.config.activation,
                output_activation=self.config.output_activation,
                loss_fn=self.config.loss_fn,
            )
            self.model.compile(optimizer=AdamOptimizer(learning_rate=self.config.learning_rate))
        else:
            # Fallback: numpy MLP
            self.model = self._build_numpy_mlp(input_dim)
        return self.model

    def _build_numpy_mlp(self, input_dim: int) -> Dict[str, Any]:
        """Build a simple numpy-based MLP for training."""
        layers = [input_dim] + list(self.config.hidden_layers) + [1]
        weights = []
        biases = []
        for i in range(len(layers) - 1):
            # Xavier initialization
            limit = np.sqrt(6.0 / (layers[i] + layers[i + 1]))
            w = self._rng.uniform(-limit, limit, (layers[i], layers[i + 1]))
            b = np.zeros((1, layers[i + 1]))
            weights.append(w)
            biases.append(b)
        return {"weights": weights, "biases": biases, "layers": layers}

    def _relu(self, x: np.ndarray) -> np.ndarray:
        """ReLU activation function."""
        return np.maximum(0, x)

    def _relu_derivative(self, x: np.ndarray) -> np.ndarray:
        """Derivative of ReLU."""
        return (x > 0).astype(float)

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Train the model on the provided data.

        Args:
            X: Feature matrix of shape (n_samples, n_features).
            y: Target vector of shape (n_samples,).
            epochs: Override the configured number of epochs.

        Returns:
            Training history dictionary.
        """
        if epochs is None:
            epochs = self.config.epochs

        if self.model is None:
            self.build_model(X.shape[1])

        epochs = epochs or self.config.epochs
        patience = self.config.early_stopping_patience
        best_loss = float("inf")
        patience_counter = 0

        self.history = {"loss": [], "val_loss": [], "epoch": []}

        for epoch in range(epochs):
            # Forward pass and backward pass
            loss = self._train_step(X, y)

            # Validation
            if epoch % 10 == 0 or epoch == epochs - 1:
                val_loss = self._compute_loss(X, y)
                self.history["loss"].append(float(loss))
                self.history["val_loss"].append(float(val_loss))
                self.history["epoch"].append(epoch)

                if self.config.verbose and epoch % 10 == 0:
                    print(f"Epoch {epoch}/{epochs} - loss: {loss:.6f} - val_loss: {val_loss:.6f}")

                # Early stopping
                if val_loss < best_loss:
                    best_loss = val_loss
                    patience_counter = 0
                    self._best_weights = [w.copy() for w in self.model["weights"]]
                    self._best_biases = [b.copy() for b in self.model["biases"]]
                else:
                    patience_counter += 1
                    if patience_counter >= patience:
                        if self.config.verbose:
                            print(f"Early stopping at epoch {epoch}")
                        break
            elif epoch % 10 == 0:
                self.history["loss"].append(float(loss))
                self.history["epoch"].append(epoch)

        # Restore best weights
        if hasattr(self, "_best_weights"):
            self.model["weights"] = self._best_weights
            self.model["biases"] = self._best_biases

        self.history["final_loss"] = float(loss)
        self.history["training_time_seconds"] = time.time() - self._start_time
        return self.history

    def _train_step(self, X: np.ndarray, y: np.ndarray) -> float:
        """Perform one training step with numpy backpropagation."""
        if not hasattr(self, "_start_time"):
            self._start_time = time.time()

        # Forward pass
        activations = [X]
        for i, (w, b) in enumerate(zip(self.model["weights"], self.model["biases"])):
            z = activations[-1] @ w + b
            if i < len(self.model["weights"]) - 1:
                a = self._relu(z)
            else:
                a = z  # Linear output
            activations.append(a)

        # Compute loss (MSE)
        output = activations[-1].flatten()
        loss = np.mean((output - y) ** 2)

        # Backward pass
        n = len(X)
        delta = (output - y) / n
        deltas = [delta]

        for i in range(len(self.model["weights"]) - 1, 0, -1):
            delta = deltas[-1] @ self.model["weights"][i].T * self._relu_derivative(activations[i])
            deltas.append(delta)
        deltas.reverse()

        # Update weights
        lr = self.config.learning_rate
        for i, (w, b) in enumerate(zip(self.model["weights"], self.model["biases"])):
            grad_w = activations[i].T @ deltas[i]
            grad_b = np.sum(deltas[i], axis=0, keepdims=True)
            self.model["weights"][i] -= lr * grad_w
            self.model["biases"][i] -= lr * grad_b

        return float(loss)

    def _compute_loss(self, X: np.ndarray, y: np.ndarray) -> float:
        """Compute MSE loss without training."""
        activations = [X]
        for i, (w, b) in enumerate(zip(self.model["weights"], self.model["biases"])):
            z = activations[-1] @ w + b
            if i < len(self.model["weights"]) - 1:
                a = self._relu(z)
            else:
                a = z
            activations.append(a)
        output = activations[-1].flatten()
        return float(np.mean((output - y) ** 2))

    def save_checkpoint(self, filepath: str):
        """Save model weights to JSON checkpoint."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        checkpoint = {
            "config": {
                "hidden_layers": self.config.hidden_layers,
                "learning_rate": self.config.learning_rate,
                "epochs": self.config.epochs,
                "activation": self.config.activation,
            },
            "weights": [w.tolist() for w in self.model["weights"]],
            "biases": [b.tolist() for b in self.model["biases"]],
            "history": self.history,
        }
        with open(filepath, "w") as fh:
            json.dump(checkpoint, fh, indent=2)
        return filepath

    def load_checkpoint(self, filepath: str):
        """Load model weights from a JSON checkpoint."""
        with open(filepath, "r") as fh:
            data = json.load(fh)
        self.model["weights"] = [np.array(w) for w in data["weights"]]
        self.model["biases"] = [np.array(b) for b in data["biases"]]
        self.history = data.get("history", {})
        return self.model


def train_pipeline(
    records: List[Dict[str, Any]],
    feature_fields: List[str],
    target_field: str,
    config: Optional[TrainingConfig] = None,
) -> Dict[str, Any]:
    """Convenience function to train a model from records."""
    trainer = PipelineTrainer(config)
    preparer = DataPreparer(config)
    X, y = preparer.prepare_from_records(records, feature_fields, target_field)
    history = trainer.train(X, y)
    return {
        "history": history,
        "feature_dim": X.shape[1],
        "n_samples": len(X),
    }
