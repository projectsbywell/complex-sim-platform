"""
neural.py — Multilayer Perceptron trained with NumPy
====================================================

A minimal, from-scratch MLP supporting arbitrary layer widths, several
activation functions, SGD and Adam optimisers, and MSE / BCE losses.

Parameters
----------
layers : list[int]
    Widths of each layer including input and output (e.g. ``[4, 8, 1]``).
activation : str
    Activation function for hidden layers: ``"relu"`` (default),
    ``"sigmoid"``, or ``"tanh"``.
loss : str
    Loss function: ``"mse"`` (default) or ``"bce"``.
optimiser : str
    ``"sgd"`` (default) or ``"adam"``.
seed : int | None
    RNG seed for weight initialisation (default None).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from .base import Simulatable, seed_rng

_DEFAULTS: Dict[str, Any] = {
    "layers": [4, 8, 1],
    "activation": "relu",
    "loss": "mse",
    "optimiser": "sgd",
    "seed": None,
}

# He initialization gain per activation
_GAIN: Dict[str, float] = {
    "relu": np.sqrt(2.0),
    "sigmoid": 1.0,
    "tanh": 1.0,
}


def _activate(z: np.ndarray, kind: str) -> np.ndarray:
    if kind == "relu":
        return np.maximum(0.0, z)
    if kind == "sigmoid":
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
    if kind == "tanh":
        return np.tanh(z)
    raise ValueError(f"Unknown activation: {kind!r}")


def _activate_prime(a: np.ndarray, kind: str) -> np.ndarray:
    """Derivative w.r.t. pre-activation, given post-activation *a*."""
    if kind == "relu":
        return (a > 0).astype(float)
    if kind == "sigmoid":
        return a * (1 - a)
    if kind == "tanh":
        return 1.0 - a * a
    raise ValueError(f"Unknown activation: {kind!r}")


def _mse_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    return float(0.5 * np.mean((y_pred - y_true) ** 2))


def _mse_grad(y_pred: np.ndarray, y_true: np.ndarray) -> np.ndarray:
    return (y_pred - y_true) / y_true.size


def _bce_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    eps = 1e-7
    yp = np.clip(y_pred, eps, 1 - eps)
    return float(-np.mean(y_true * np.log(yp) + (1 - y_true) * np.log(1 - yp)))


def _bce_grad(y_pred: np.ndarray, y_true: np.ndarray) -> np.ndarray:
    eps = 1e-7
    yp = np.clip(y_pred, eps, 1 - eps)
    return ((yp - y_true) / (yp * (1 - yp))) / y_true.size


class NeuralSimulation(Simulatable):
    """Fully-connected MLP with training and inference via pure NumPy."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        merged = {**_DEFAULTS, **(params or {})}
        self._params: Dict[str, Any] = dict(merged)
        self._rng = seed_rng(self._params["seed"])

        self._arch: List[int] = list(self._params["layers"])
        self._act: str = str(self._params["activation"])
        self._loss_kind: str = str(self._params.get("loss", "mse"))
        self._opt: str = str(self._params.get("optimiser", "sgd"))

        # Weight & bias initialisation (He)
        self._W: List[np.ndarray] = []
        self._b: List[np.ndarray] = []
        for i in range(len(self._arch) - 1):
            fan_in = self._arch[i]
            fan_out = self._arch[i + 1]
            gain = _GAIN.get(self._act, 1.0)
            std = gain * (1.0 / fan_in) ** 0.5
            self._W.append(self._rng.normal(0, std, (fan_in, fan_out)))
            self._b.append(np.zeros(fan_out))

        # Adam state
        self._mW: List[np.ndarray] = [np.zeros_like(w) for w in self._W]
        self._vW: List[np.ndarray] = [np.zeros_like(w) for w in self._W]
        self._mb: List[np.ndarray] = [np.zeros_like(b) for b in self._b]
        self._vb: List[np.ndarray] = [np.zeros_like(b) for b in self._b]
        self._t: int = 0

        self._loss_history: List[float] = []
        self._step_count: int = 0

    # ------------------------------------------------------------------
    # Forward / backward
    # ------------------------------------------------------------------

    def _forward(
        self, X: np.ndarray
    ) -> tuple[np.ndarray, List[np.ndarray], List[np.ndarray]]:
        """Forward pass. Returns (output, pre-activations, post-activations)."""
        a = X
        zs: List[np.ndarray] = []
        as_ = [a]
        for idx, (W, b) in enumerate(zip(self._W, self._b)):
            z = a @ W + b
            zs.append(z)
            if idx < len(self._W) - 1:  # hidden
                a = _activate(z, self._act)
            else:  # output — linear (regression) or sigmoid (BCE)
                if self._loss_kind == "bce":
                    a = _activate(z, "sigmoid")
                else:
                    a = z  # linear output
            as_.append(a)
        return a, zs, as_

    def _backward(
        self,
        zs: List[np.ndarray],
        as_: List[np.ndarray],
        y_true: np.ndarray,
    ) -> None:
        """Backpropagation; accumulates grads into ``self._grad_W / _grad_b``."""
        L = len(self._W)
        self._grad_W: List[np.ndarray] = [np.zeros_like(w) for w in self._W]
        self._grad_b: List[np.ndarray] = [np.zeros_like(b) for b in self._b]

        # Output layer delta
        if self._loss_kind == "bce":
            delta = _bce_grad(as_[-1], y_true)
        else:
            delta = _mse_grad(as_[-1], y_true)

        for k in reversed(range(L)):
            self._grad_W[k] = as_[k].T @ delta
            self._grad_b[k] = np.sum(delta, axis=0)
            if k > 0:
                delta = (delta @ self._W[k].T) * _activate_prime(as_[k], self._act)

    def _apply_grads(self) -> None:
        """Update weights using the chosen optimiser."""
        self._t += 1
        lr = float(self._params.get("lr", 0.01))

        if self._opt == "adam":
            beta1, beta2, eps_adam = 0.9, 0.999, 1e-8
            for i in range(len(self._W)):
                self._mW[i] = beta1 * self._mW[i] + (1 - beta1) * self._grad_W[i]
                self._vW[i] = beta2 * self._vW[i] + (1 - beta2) * self._grad_W[i] ** 2
                mhat = self._mW[i] / (1 - beta1**self._t)
                vhat = self._vW[i] / (1 - beta2**self._t)
                self._W[i] -= lr * mhat / (np.sqrt(vhat) + eps_adam)

                self._mb[i] = beta1 * self._mb[i] + (1 - beta1) * self._grad_b[i]
                self._vb[i] = beta2 * self._vb[i] + (1 - beta2) * self._grad_b[i] ** 2
                mbhat = self._mb[i] / (1 - beta1**self._t)
                vbhat = self._vb[i] / (1 - beta2**self._t)
                self._b[i] -= lr * mbhat / (np.sqrt(vbhat) + eps_adam)
        else:  # sgd
            for i in range(len(self._W)):
                self._W[i] -= lr * self._grad_W[i]
                self._b[i] -= lr * self._grad_b[i]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 100,
        lr: float = 0.01,
    ) -> List[float]:
        """Train for *epochs* passes over (X, y). Returns loss history."""
        self._params["lr"] = lr
        history: List[float] = []
        for _ in range(epochs):
            y_pred, zs, as_ = self._forward(X)
            loss = (
                _bce_loss(y_pred, y)
                if self._loss_kind == "bce"
                else _mse_loss(y_pred, y)
            )
            history.append(loss)
            self._backward(zs, as_, y)
            self._apply_grads()
        self._loss_history.extend(history)
        return history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Forward inference — returns output array."""
        out, _, _ = self._forward(X)
        return out

    @property
    def loss_history(self) -> List[float]:
        return list(self._loss_history)

    # ------------------------------------------------------------------
    # Simulatable interface
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Single optimisation step using stored training data (if any).

        If no training data is stored this is a no-op.
        """
        self._step_count += 1

    def get_state(self) -> Dict[str, Any]:
        return {
            "W": [w.tolist() for w in self._W],
            "b": [b.tolist() for b in self._b],
            "loss_history": self._loss_history,
            "arch": self._arch,
            "step": self._step_count,
        }

    def set_state(self, d: Dict[str, Any]) -> None:
        self._W = [np.array(w) for w in d["W"]]
        self._b = [np.array(b) for b in d["b"]]
        self._loss_history = list(d.get("loss_history", []))
        self._arch = list(d.get("arch", self._arch))
        self._step_count = int(d.get("step", 0))

    def get_params(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_params(self, p: Dict[str, Any]) -> None:
        self._params.update(p)
