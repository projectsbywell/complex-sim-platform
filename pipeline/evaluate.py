"""
evaluate.py — métricas regressão/classificação + cross-val simples
Stdlib + numpy (opcional, com fallback puro python).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple, Any

try:
    import numpy as np  # type: ignore
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# --- helpers ---
def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0

def _as_list(x) -> List[float]:
    if HAS_NUMPY and isinstance(x, np.ndarray):
        return x.tolist()
    return list(x)

# --- Regressão ---
def mae(y_true, y_pred) -> float:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    assert len(yt) == len(yp) and len(yt) > 0
    return sum(abs(a - b) for a, b in zip(yt, yp)) / len(yt)

def mse(y_true, y_pred) -> float:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    return sum((a - b) ** 2 for a, b in zip(yt, yp)) / len(yt)

def rmse(y_true, y_pred) -> float:
    return math.sqrt(mse(y_true, y_pred))

def r2_score(y_true, y_pred) -> float:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    m = _mean(yt)
    ss_tot = sum((a - m) ** 2 for a in yt)
    ss_res = sum((a - b) ** 2 for a, b in zip(yt, yp))
    if ss_tot == 0:
        return 0.0 if ss_res != 0 else 1.0
    return 1 - ss_res / ss_tot

def mape(y_true, y_pred) -> float:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    vals = [abs((a - b) / a) for a, b in zip(yt, yp) if a != 0]
    return sum(vals) / len(vals) * 100 if vals else 0.0

def regression_metrics(y_true, y_pred) -> Dict[str, float]:
    return {
        "mae": round(mae(y_true, y_pred), 6),
        "mse": round(mse(y_true, y_pred), 6),
        "rmse": round(rmse(y_true, y_pred), 6),
        "r2": round(r2_score(y_true, y_pred), 6),
        "mape": round(mape(y_true, y_pred), 6),
    }

# --- Classificação ---
def accuracy(y_true, y_pred) -> float:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    return sum(1 for a, b in zip(yt, yp) if a == b) / len(yt) if yt else 0.0

def precision_recall_f1(y_true, y_pred, pos_label=1) -> Dict[str, float]:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    tp = sum(1 for a, b in zip(yt, yp) if a == pos_label and b == pos_label)
    fp = sum(1 for a, b in zip(yt, yp) if a != pos_label and b == pos_label)
    fn = sum(1 for a, b in zip(yt, yp) if a == pos_label and b != pos_label)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": round(prec, 6), "recall": round(rec, 6), "f1": round(f1, 6)}

def confusion_matrix(y_true, y_pred, labels: List[Any] | None = None) -> Dict[str, Any]:
    yt, yp = _as_list(y_true), _as_list(y_pred)
    labs = labels or sorted(set(yt) | set(yp))
    idx = {l: i for i, l in enumerate(labs)}
    n = len(labs)
    mat = [[0]*n for _ in range(n)]
    for a, b in zip(yt, yp):
        mat[idx[a]][idx[b]] += 1
    return {"labels": labs, "matrix": mat}

def classification_metrics(y_true, y_pred) -> Dict[str, Any]:
    out: Dict[str, Any] = {"accuracy": round(accuracy(y_true, y_pred), 6)}
    out.update(precision_recall_f1(y_true, y_pred))
    out["confusion"] = confusion_matrix(y_true, y_pred)
    return out

# --- Cross-validation simples ---
def kfold_indices(n: int, k: int = 5, shuffle: bool = True, seed: int = 42) -> List[Tuple[List[int], List[int]]]:
    idx = list(range(n))
    if shuffle:
        rnd = random.Random(seed)
        rnd.shuffle(idx)
    fold = n // k
    splits = []
    for i in range(k):
        start, end = i*fold, (i+1)*fold if i < k-1 else n
        test = idx[start:end]
        train = idx[:start] + idx[end:]
        splits.append((train, test))
    return splits

def cross_val_score(predict_fn, X, y, k: int = 5, metric_fn=mae, seed: int = 42) -> Dict[str, Any]:
    """
    predict_fn: (X_train, y_train, X_test) -> y_pred
    metric_fn: (y_true, y_pred) -> float  (menor é melhor por padrão)
    """
    n = len(y)
    splits = kfold_indices(n, k=k, seed=seed)
    scores = []
    for train_idx, test_idx in splits:
        X_tr = [X[i] for i in train_idx]
        y_tr = [y[i] for i in train_idx]
        X_te = [X[i] for i in test_idx]
        y_te = [y[i] for i in test_idx]
        y_pred = predict_fn(X_tr, y_tr, X_te)
        scores.append(metric_fn(y_te, y_pred))
    mean = _mean(scores)
    var = sum((s-mean)**2 for s in scores)/len(scores) if len(scores)>1 else 0.0
    return {"scores": [round(s,6) for s in scores], "mean": round(mean,6), "std": round(math.sqrt(var),6), "k": k}


if __name__ == "__main__":
    # regressão
    yt = [3, -0.5, 2, 7]
    yp = [2.5, 0.0, 2, 8]
    print(regression_metrics(yt, yp))
    # classificação
    print(classification_metrics([0,1,1,0,1],[0,1,0,0,1]))
    # cv dummy: média do train
    def dummy_predict(Xtr, ytr, Xte):
        m = _mean(ytr)
        return [m]*len(Xte)
    X = [[i] for i in range(20)]
    y = [i*0.5+random.gauss(0,1) for i in range(20)]
    print(cross_val_score(dummy_predict, X, y, k=4))
    print("evaluate OK")
