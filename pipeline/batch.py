"""Pipeline batch processing module for complex-sim-platform.

Provides cleaning, normalization, and windowed aggregation functions
for batch data collected from collectors.
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict

import numpy as np


def clean_data(
    records: List[Dict[str, Any]],
    drop_null_ratio: float = 0.5,
    fill_strategy: str = "mean",
) -> List[Dict[str, Any]]:
    """Clean a batch of records by handling missing values and removing
    records with excessive null fields.

    Args:
        records: List of record dicts from a collector.
        drop_null_ratio: Drop records where this fraction of fields are null.
        fill_strategy: Strategy for filling missing values: 'mean', 'median',
            'zero', or 'forward'.

    Returns:
        Cleaned list of records.
    """
    if not records:
        return []

    # Identify numeric fields across all records
    numeric_fields = set()
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(
                v, bool
            ):
                numeric_fields.add(k)

    # Compute fill values per field
    fill_values = {}
    for field in numeric_fields:
        values = [
            rec[field]
            for rec in records
            if field in rec
            and rec[field] is not None
            and isinstance(rec[field], (int, float, np.number))
        ]
        if not values:
            fill_values[field] = 0.0
            continue
        arr = np.array(values, dtype=float)
        if fill_strategy == "mean":
            fill_values[field] = float(np.mean(arr))
        elif fill_strategy == "median":
            fill_values[field] = float(np.median(arr))
        elif fill_strategy == "zero":
            fill_values[field] = 0.0
        elif fill_strategy == "forward":
            fill_values[field] = float(arr[0]) if len(arr) > 0 else 0.0

    cleaned = []
    for rec in records:
        null_count = sum(1 for v in rec.values() if v is None)
        null_ratio = null_count / max(1, len(rec))
        if null_ratio >= drop_null_ratio:
            continue  # Drop this record

        new_rec = dict(rec)
        for field, fill_val in fill_values.items():
            if field in new_rec and new_rec[field] is None:
                new_rec[field] = fill_val
        cleaned.append(new_rec)

    return cleaned


def normalize_data(
    records: List[Dict[str, Any]],
    fields: Optional[List[str]] = None,
    method: str = "zscore",
) -> List[Dict[str, Any]]:
    """Normalize numeric fields in records.

    Args:
        records: List of record dicts.
        fields: Specific fields to normalize. If None, normalize all numeric.
        method: 'zscore' for standard score normalization, 'minmax' for
            [0,1] scaling, or 'log' for logarithmic transform.

    Returns:
        List of records with normalized fields.
    """
    if not records:
        return []

    # Determine fields to normalize
    if fields is None:
        fields = set()
        for rec in records:
            for k, v in rec.items():
                if isinstance(v, (int, float, np.number)) and not isinstance(v, bool):
                    fields.add(k)
        fields = list(fields)

    normalized = []
    for field in fields:
        values = np.array([float(rec.get(field, 0)) for rec in records])
        if method == "zscore":
            mean, std = np.mean(values), np.std(values)
            if std > 0:
                norm_vals = (values - mean) / std
            else:
                norm_vals = np.zeros_like(values)
        elif method == "minmax":
            min_v, max_v = np.min(values), np.max(values)
            if max_v > min_v:
                norm_vals = (values - min_v) / (max_v - min_v)
            else:
                norm_vals = np.zeros_like(values)
        elif method == "log":
            shifted = np.where(values <= 0, 0, values)
            norm_vals = np.log1p(shifted)
            if np.max(norm_vals) > 0:
                norm_vals = norm_vals / np.max(norm_vals)
        else:
            norm_vals = values

        for i, rec in enumerate(records):
            rec = dict(rec)
            rec[field] = float(norm_vals[i])
            normalized.append(rec) if False else None
            # Update in place

    # Actually update records
    result = []
    for i, rec in enumerate(records):
        new_rec = dict(rec)
        for field in fields:
            values = np.array([float(r.get(field, 0)) for r in records])
            if method == "zscore":
                mean, std = np.mean(values), np.std(values)
                new_rec[field] = float((values[i] - mean) / std) if std > 0 else 0.0
            elif method == "minmax":
                min_v, max_v = np.min(values), np.max(values)
                new_rec[field] = (
                    float((values[i] - min_v) / (max_v - min_v))
                    if max_v > min_v
                    else 0.0
                )
            elif method == "log":
                v = max(float(rec.get(field, 0)), 0)
                new_rec[field] = float(np.log1p(v))
        result.append(new_rec)
    return result


def aggregate_window(
    records: List[Dict[str, Any]],
    window_size: int,
    agg_func: str = "mean",
    group_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Aggregate records into fixed-size windows.

    Args:
        records: Sorted list of record dicts.
        window_size: Number of records per window.
        agg_func: Aggregation function: 'mean', 'sum', 'max', 'min', 'count'.
        group_by: Optional field name to group records before windowing.

    Returns:
        List of aggregated window records.
    """
    if not records or window_size < 1:
        return []

    # Group records if requested
    groups = defaultdict(list)
    if group_by:
        for rec in records:
            key = rec.get(group_by, "_default")
            groups[key].append(rec)
    else:
        groups["_default"] = records

    results = []
    for key, group_records in groups.items():
        # Extract numeric values per field
        numeric_fields = set()
        for rec in group_records:
            for k, v in rec.items():
                if isinstance(v, (int, float, np.number)) and not isinstance(v, bool):
                    numeric_fields.add(k)

        for start in range(0, len(group_records), window_size):
            window = group_records[start : start + window_size]
            window_record = {"_window_start": start, "_window_size": len(window)}
            if group_by:
                window_record["_group"] = key

            for field in numeric_fields:
                vals = np.array([float(rec.get(field, 0)) for rec in window])
                if agg_func == "mean":
                    window_record[field] = float(np.mean(vals))
                elif agg_func == "sum":
                    window_record[field] = float(np.sum(vals))
                elif agg_func == "max":
                    window_record[field] = float(np.max(vals))
                elif agg_func == "min":
                    window_record[field] = float(np.min(vals))
                elif agg_func == "count":
                    window_record[field] = float(len(vals))
            results.append(window_record)

    return results


def compute_rolling_average(
    values: List[float],
    window: int,
) -> List[float]:
    """Compute rolling average using numpy convolution."""
    if window < 1 or not values:
        return [0.0] * len(values)
    kernel = np.ones(window) / window
    padded = np.pad(values, (window - 1, 0), mode="constant")
    return list(np.convolve(padded, kernel, mode="valid"))


def batch_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics for a batch of records."""
    stats = {"record_count": len(records)}
    if not records:
        return stats

    numeric_fields = {}
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (int, float, np.number)) and not isinstance(v, bool):
                numeric_fields.setdefault(k, []).append(float(v))

    for field, vals in numeric_fields.items():
        arr = np.array(vals)
        stats[field] = {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "median": float(np.median(arr)),
            "q25": float(np.percentile(arr, 25)),
            "q75": float(np.percentile(arr, 75)),
        }
    return stats
