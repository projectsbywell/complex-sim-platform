"""Pipeline collectors module for complex-sim-platform.

Provides data collection from public APIs, local CSV files, and synthetic
stream generators. All collectors return standardized dict records.
"""

import json
import time
import random
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any, List, Optional
from datetime import datetime, timezone

import numpy as np


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    def __init__(self, seed: Optional[int] = None):
        self._seed = seed
        self._rng = np.random.default_rng(seed)
        self.records_collected = 0

    @abstractmethod
    def collect(self, n: int = 1) -> List[Dict[str, Any]]:
        """Collect n records and return as a list of dicts."""
        ...

    @abstractmethod
    def stream(self) -> Iterator[Dict[str, Any]]:
        """Yield records indefinitely as a generator."""
        ...

    def _record_header(self) -> Dict[str, Any]:
        """Standard metadata prepended to every record."""
        return {
            "_collector": self.__class__.__name__,
            "_timestamp": datetime.now(timezone.utc).isoformat(),
            "_record_id": self.records_collected,
        }

    def _normalize_value(self, value: Any, target_type: type) -> Any:
        """Coerce a value to the target type safely."""
        if value is None:
            return None
        try:
            if target_type == float:
                return float(value)
            elif target_type == int:
                return int(float(value))
            elif target_type == str:
                return str(value)
            elif target_type == bool:
                return bool(value)
        except (ValueError, TypeError):
            return None
        return value


class PublicAPICollector(BaseCollector):
    """Collects data from public HTTP APIs using stdlib urllib."""

    def __init__(
        self,
        base_url: str,
        endpoint: str = "",
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint.strip("/")
        self.timeout = timeout
        self.headers = headers or {"User-Agent": "complex-sim-platform/1.0"}
        self._url = f"{self.base_url}/{self.endpoint}" if self.endpoint else self.base_url

    def collect(self, n: int = 1) -> List[Dict[str, Any]]:
        """Fetch n records from the public API endpoint."""
        records = []
        for i in range(n):
            try:
                req = urllib.request.Request(
                    self._url, headers={**self.headers, "Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                    record = self._record_header()
                    record["_source"] = self._url
                    record["data"] = raw
                    records.append(record)
                    self.records_collected += 1
            except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
                record = self._record_header()
                record["_source"] = self._url
                record["_error"] = str(e)
                records.append(record)
        return records

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Yield API records indefinitely with rate limiting."""
        while True:
            batch = self.collect(n=1)
            for rec in batch:
                yield rec
            time.sleep(0.5)


class CSVCollector(BaseCollector):
    """Collects data from local CSV files using stdlib csv module."""

    def __init__(self, filepath: str, delimiter: str = ",", **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath
        self.delimiter = delimiter
        self._column_names: Optional[List[str]] = None

    def collect(self, n: int = 1) -> List[Dict[str, Any]]:
        """Read up to n rows from the CSV file."""
        import csv

        records = []
        with open(self.filepath, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=self.delimiter)
            if self._column_names is None:
                self._column_names = reader.fieldnames or []
            for row in reader:
                if len(records) >= n:
                    break
                record = self._record_header()
                record["_source"] = self.filepath
                record["_row_number"] = reader.line_num
                # Convert numeric strings to proper types
                for key, value in row.items():
                    record[key] = self._try_numeric(value)
                records.append(record)
                self.records_collected += 1
        return records

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Yield CSV rows in an infinite loop."""
        while True:
            batch = self.collect(n=max(1, self.records_collected + 1 - self.records_collected))
            for rec in batch:
                yield rec

    def _try_numeric(self, value: str) -> Any:
        """Attempt to convert a string to int or float."""
        try:
            if "." in value:
                return float(value)
            return int(value)
        except (ValueError, AttributeError):
            return value

    def get_column_names(self) -> List[str]:
        """Return the detected column names."""
        return self._column_names or []


class SyntheticStreamCollector(BaseCollector):
    """Generates synthetic data streams for testing and prototyping."""

    def __init__(
        self,
        schema: Dict[str, type],
        drift: float = 0.0,
        noise_scale: float = 0.1,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.schema = schema
        self.drift = drift
        self.noise_scale = noise_scale
        self._step = 0
        self._trend = {k: self._rng.normal(0, 0.01) for k in schema if schema[k] in (float, int)}

    def collect(self, n: int = 1) -> List[Dict[str, Any]]:
        """Generate n synthetic records following the schema."""
        records = []
        for _ in range(n):
            record = self._record_header()
            record["_source"] = "synthetic://stream"
            for field, ftype in self.schema.items():
                base = self._rng.normal(0, 1) if ftype == float else self._rng.integers(0, 100)
                noise = self._rng.normal(0, self.noise_scale)
                trend = self._trend.get(field, 0) * self._step * self.drift
                if ftype == float:
                    record[field] = float(base + noise + trend)
                elif ftype == int:
                    record[field] = int(base + noise + trend)
                elif ftype == bool:
                    record[field] = bool(self._rng.integers(0, 2))
                else:
                    record[field] = str(self._rng.integers(0, 1000))
            records.append(record)
            self._step += 1
            self.records_collected += 1
        return records

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Yield synthetic records indefinitely."""
        while True:
            yield self.collect(n=1)[0]

    def set_drift(self, drift: float):
        """Adjust the trend drift rate."""
        self.drift = drift

    def set_noise(self, scale: float):
        """Adjust the noise scale."""
        self.noise_scale = scale


def make_collector(
    kind: str, config: Dict[str, Any], **kwargs
) -> BaseCollector:
    """Factory function to create a collector by name."""
    if kind == "api":
        return PublicAPICollector(**config, **kwargs)
    elif kind == "csv":
        return CSVCollector(**config, **kwargs)
    elif kind == "synthetic":
        return SyntheticStreamCollector(**config, **kwargs)
    else:
        raise ValueError(f"Unknown collector type: {kind!r}")
