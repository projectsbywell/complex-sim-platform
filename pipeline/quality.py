"""Pipeline data quality module for complex-sim-platform.

Provides schema validation, missing rate analysis, outlier detection
via z-score, and comprehensive quality reporting.
"""

import json
import time
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np


class SchemaValidator:
    """Validates records against a defined schema."""

    def __init__(self, schema: Dict[str, type]):
        """
        Args:
            schema: Dict mapping field names to expected types.
                Example: {"temperature": float, "label": str, "active": bool}
        """
        self.schema = schema
        self.violations: List[Dict[str, Any]] = []

    def validate(self, record: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a single record against the schema.

        Returns:
            (is_valid, list_of_violation_messages)
        """
        errors = []
        for field, expected_type in self.schema.items():
            if field not in record:
                errors.append(f"Missing required field: {field}")
                continue
            value = record[field]
            if value is None:
                errors.append(
                    f"Field {field} is None, expected {expected_type.__name__}"
                )
                continue
            # Allow numpy numeric types
            if expected_type in (int, float) and isinstance(
                value, (int, float, np.integer, np.floating)
            ):
                continue
            if expected_type == bool and isinstance(value, bool):
                continue
            if expected_type == str and isinstance(value, str):
                continue
            if isinstance(value, expected_type):
                continue
            # Try coercion
            try:
                if expected_type == float:
                    float(value)
                elif expected_type == int:
                    int(value)
                elif expected_type == bool:
                    bool(value)
                elif expected_type == str:
                    str(value)
            except (ValueError, TypeError):
                errors.append(
                    f"Field {field} has type {type(value).__name__}, expected {expected_type.__name__}"
                )
        self.violations.extend(
            {"record_id": record.get("_record_id", "unknown"), "errors": errors}
            for errors in [errors]
        )
        return len(errors) == 0, errors

    def validate_batch(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate a batch of records. Returns summary."""
        results = []
        valid_count = 0
        for rec in records:
            is_valid, errors = self.validate(rec)
            if is_valid:
                valid_count += 1
            results.append(
                {
                    "record_id": rec.get("_record_id"),
                    "valid": is_valid,
                    "errors": errors,
                }
            )

        total = len(records)
        return {
            "total_records": total,
            "valid_records": valid_count,
            "invalid_records": total - valid_count,
            "validity_rate": valid_count / max(1, total),
            "results": results,
        }


class MissingRateAnalyzer:
    """Analyzes missing data rates across fields and records."""

    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        self._all_fields = self._collect_fields()

    def _collect_fields(self) -> set:
        """Collect all unique field names across records."""
        fields = set()
        for rec in self.records:
            fields.update(rec.keys())
        return fields

    def field_missing_rates(self) -> Dict[str, float]:
        """Compute the fraction of records missing each field."""
        if not self.records:
            return {}
        n = len(self.records)
        rates = {}
        for field in self._all_fields:
            missing = sum(
                1 for rec in self.records if field not in rec or rec[field] is None
            )
            rates[field] = missing / n
        return rates

    def record_missing_counts(self) -> Dict[int, int]:
        """Count how many fields are missing per record."""
        counts = {}
        for i, rec in enumerate(self.records):
            missing = sum(1 for f in self._all_fields if f not in rec or rec[f] is None)
            counts[i] = missing
        return counts

    def overall_missing_rate(self) -> float:
        """Overall fraction of field-value pairs that are missing."""
        if not self.records:
            return 0.0
        total_fields = len(self.records) * len(self._all_fields)
        if total_fields == 0:
            return 0.0
        missing = sum(
            1
            for rec in self.records
            for f in self._all_fields
            if f not in rec or rec[f] is None
        )
        return missing / total_fields

    def report(self) -> Dict[str, Any]:
        """Generate a comprehensive missing data report."""
        field_rates = self.field_missing_rates()
        rec_counts = self.record_missing_counts()
        critical_fields = {f: r for f, r in field_rates.items() if r > 0.5}
        return {
            "total_records": len(self.records),
            "total_fields": len(self._all_fields),
            "overall_missing_rate": self.overall_missing_rate(),
            "field_missing_rates": field_rates,
            "critical_fields": critical_fields,
            "records_exceeding_50pct_missing": sum(
                1 for c in rec_counts.values() if c > len(self._all_fields) * 0.5
            ),
        }


class OutlierDetector:
    """Detects outliers using z-score and IQR methods."""

    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        self.outlier_report: Dict[str, Any] = {}

    def z_score_outliers(
        self, field: str, threshold: float = 3.0
    ) -> List[Dict[str, Any]]:
        """Identify outliers in a numeric field using z-score method.

        Args:
            field: The numeric field to analyze.
            threshold: Z-score threshold (default 3.0 = 3 standard deviations).

        Returns:
            List of dicts with outlier information.
        """
        values = []
        indices = []
        for i, rec in enumerate(self.records):
            if field in rec and isinstance(rec[field], (int, float, np.number)):
                values.append(float(rec[field]))
                indices.append(i)

        if len(values) < 2:
            return []

        arr = np.array(values)
        mean = np.mean(arr)
        std = np.std(arr)
        if std == 0:
            return []

        z_scores = np.abs((arr - mean) / std)
        outliers = []
        for idx, z in zip(indices, z_scores):
            if z > threshold:
                outliers.append(
                    {
                        "record_index": idx,
                        "record_id": self.records[idx].get("_record_id"),
                        "field": field,
                        "value": float(arr[idx]),
                        "z_score": float(z),
                        "mean": float(mean),
                        "std": float(std),
                    }
                )
        return outliers

    def iqr_outliers(self, field: str, multiplier: float = 1.5) -> List[Dict[str, Any]]:
        """Identify outliers using the Interquartile Range method."""
        values = []
        indices = []
        for i, rec in enumerate(self.records):
            if field in rec and isinstance(rec[field], (int, float, np.number)):
                values.append(float(rec[field]))
                indices.append(i)

        if len(values) < 4:
            return []

        arr = np.array(values)
        q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr

        outliers = []
        for idx, val in zip(indices, arr):
            if val < lower or val > upper:
                outliers.append(
                    {
                        "record_index": idx,
                        "record_id": self.records[idx].get("_record_id"),
                        "field": field,
                        "value": float(val),
                        "iqr_lower": float(lower),
                        "iqr_upper": float(upper),
                    }
                )
        return outliers

    def multi_field_outliers(self, threshold: float = 3.0) -> Dict[str, Any]:
        """Run z-score outlier detection across all numeric fields."""
        numeric_fields = set()
        for rec in self.records:
            for k, v in rec.items():
                if isinstance(v, (int, float, np.number)) and not isinstance(v, bool):
                    numeric_fields.add(k)

        results = {}
        total_outliers = 0
        for field in sorted(numeric_fields):
            outliers = self.z_score_outliers(field, threshold)
            results[field] = {
                "outlier_count": len(outliers),
                "outlier_rate": len(outliers) / max(1, len(self.records)),
                "outliers": outliers[:10],  # Top 10 for readability
            }
            total_outliers += len(outliers)

        self.outlier_report = {
            "method": "z-score",
            "threshold": threshold,
            "total_outliers": total_outliers,
            "total_records": len(self.records),
            "fields_analyzed": len(numeric_fields),
            "fields": results,
        }
        return self.outlier_report


class QualityReport:
    """Generates a comprehensive data quality report."""

    def __init__(
        self, records: List[Dict[str, Any]], schema: Optional[Dict[str, type]] = None
    ):
        self.records = records
        self.schema = schema
        self._timestamp = datetime.now(timezone.utc).isoformat()

    def generate(self) -> Dict[str, Any]:
        """Generate a full quality report."""
        report = {
            "report_id": f"qr-{int(time.time())}",
            "timestamp": self._timestamp,
            "dataset": {
                "total_records": len(self.records),
                "total_fields": len(self.records[0]) if self.records else 0,
                "schema_provided": self.schema is not None,
            },
            "missing_data": {},
            "outliers": {},
            "schema_validation": {},
            "statistics": {},
        }

        # Missing data analysis
        if self.records:
            analyzer = MissingRateAnalyzer(self.records)
            report["missing_data"] = analyzer.report()

        # Outlier detection
        if self.records:
            detector = OutlierDetector(self.records)
            report["outliers"] = detector.multi_field_outliers()

        # Schema validation
        if self.schema and self.records:
            validator = SchemaValidator(self.schema)
            report["schema_validation"] = validator.validate_batch(self.records)

        # Basic statistics
        if self.records:
            numeric_fields = {}
            for rec in self.records:
                for k, v in rec.items():
                    if isinstance(v, (int, float, np.number)) and not isinstance(
                        v, bool
                    ):
                        numeric_fields.setdefault(k, []).append(float(v))
            report["statistics"] = {
                field: {
                    "mean": float(np.mean(vals)),
                    "std": float(np.std(vals)),
                    "min": float(np.min(vals)),
                    "max": float(np.max(vals)),
                    "count": len(vals),
                }
                for field, vals in numeric_fields.items()
            }

        # Quality score (0-100)
        score = 100.0
        if report["missing_data"]:
            score -= report["missing_data"].get("overall_missing_rate", 0) * 30
        if report["outliers"]:
            outlier_rate = report["outliers"].get("total_outlier_rate", 0)
            score -= outlier_rate * 20
        if report["schema_validation"]:
            validity = report["schema_validation"].get("validity_rate", 1.0)
            score -= (1 - validity) * 30
        report["quality_score"] = max(0.0, min(100.0, round(score, 2)))

        return report

    def save(self, filepath: str):
        """Save the quality report as JSON."""
        report = self.generate()
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        return filepath

    def to_json(self) -> str:
        """Serialize the report to JSON string."""
        return json.dumps(self.generate(), indent=2, default=str)
