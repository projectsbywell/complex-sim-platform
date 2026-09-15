"""Pipeline real-time streaming module for complex-sim-platform.

Provides a time-based consumer with ring buffer for real-time data
processing with backpressure handling.
"""

import time
import threading
from collections import deque
from typing import Generator, Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np


@dataclass
class BufferConfig:
    """Configuration for the streaming buffer."""
    max_size: int = 10000
    flush_interval_ms: int = 1000
    compression: bool = False
    dtype: str = "float64"


@dataclass
class BufferMetrics:
    """Runtime metrics for the streaming buffer."""
    items_processed: int = 0
    items_dropped: int = 0
    current_size: int = 0
    peak_size: int = 0
    avg_processing_time_ms: float = 0.0
    total_bytes: int = 0
    start_time: str = ""


class StreamConsumer:
    """Real-time stream consumer with ring buffer and time-based flushing."""

    def __init__(
        self,
        buffer_config: Optional[BufferConfig] = None,
        on_flush: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        seed: Optional[int] = None,
    ):
        self.config = buffer_config or BufferConfig()
        self.on_flush = on_flush
        self._rng = np.random.default_rng(seed)
        self._buffer: deque = deque(maxlen=self.config.max_size)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.metrics = BufferMetrics()
        self.metrics.start_time = datetime.now(timezone.utc).isoformat()
        self._total_process_time = 0.0
        self._processed_count = 0

    def push(self, record: Dict[str, Any]) -> bool:
        """Push a record into the buffer. Returns True if accepted, False if dropped."""
        with self._lock:
            if len(self._buffer) >= self.config.max_size:
                self.metrics.items_dropped += 1
                return False
            self._buffer.append(record)
            self.metrics.current_size = len(self._buffer)
            if self.metrics.current_size > self.metrics.peak_size:
                self.metrics.peak_size = self.metrics.current_size
            return True

    def push_batch(self, records: List[Dict[str, Any]]) -> int:
        """Push multiple records. Returns the number successfully added."""
        accepted = 0
        for rec in records:
            if self.push(rec):
                accepted += 1
        return accepted

    def consume(self, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        """Pop a single record from the buffer. Blocking with optional timeout."""
        with self._lock:
            if self._buffer:
                record = self._buffer.popleft()
                self.metrics.current_size = len(self._buffer)
                self.metrics.items_processed += 1
                return record
        return None

    def flush(self) -> List[Dict[str, Any]]:
        """Flush all current buffer contents. Calls on_flush callback if set."""
        with self._lock:
            records = list(self._buffer)
            self._buffer.clear()
            self.metrics.current_size = 0

        if records:
            self.metrics.items_processed += len(records)
            if self.on_flush:
                self.on_flush(records)
        return records

    def start_consumer(
        self, source: Generator[Dict[str, Any], None, None], daemon: bool = True
    ) -> threading.Thread:
        """Start a background thread consuming from a generator source."""
        self._running = True

        def _run():
            for record in source:
                if not self._running:
                    break
                self.push(record)
                # Simulate processing time for realistic metrics
                proc_start = time.monotonic()
                # Process the record (placeholder for actual computation)
                proc_time = (time.monotonic() - proc_start) * 1000
                self._total_process_time += proc_time
                self._processed_count += 1
                if self._processed_count > 0:
                    self.metrics.avg_processing_time_ms = (
                        self._total_process_time / self._processed_count
                    )
                time.sleep(0.001)  # Backpressure

        self._thread = threading.Thread(target=_run, daemon=daemon)
        self._thread.start()
        return self._thread

    def stop_consumer(self, timeout: float = 5.0):
        """Stop the consumer thread gracefully, flushing remaining data."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=timeout)
        self.flush()  # Flush remaining

    def get_buffer_snapshot(self) -> List[Dict[str, Any]]:
        """Get a copy of the current buffer contents."""
        with self._lock:
            return list(self._buffer)

    def get_metrics(self) -> BufferMetrics:
        """Return a snapshot of current buffer metrics."""
        self.metrics.items_processed = self._processed_count
        self.metrics.current_size = len(self._buffer)
        return self.metrics

    def time_series_generator(
        self,
        interval_sec: float = 0.1,
        n_points: int = 1000,
        frequency: float = 1.0,
        amplitude: float = 1.0,
        noise_level: float = 0.05,
    ) -> Generator[Dict[str, Any], None, None]:
        """Generate a synthetic time-series stream."""
        rng = self._rng
        for i in range(n_points):
            t = i * interval_sec
            value = (
                amplitude * np.sin(2 * np.pi * frequency * t)
                + rng.normal(0, noise_level)
            )
            yield {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "t": t,
                "value": float(value),
                "frequency": frequency,
                "amplitude": amplitude,
            }
            time.sleep(interval_sec)

    def sliding_window(
        self,
        window_size: int,
    ) -> Generator[List[Dict[str, Any]], None, None]:
        """Yield sliding windows of buffer contents."""
        while self._running or len(self._buffer) > 0:
            with self._lock:
                buf = list(self._buffer)
            if len(buf) >= window_size:
                for i in range(len(buf) - window_size + 1):
                    yield buf[i:i + window_size]
                time.sleep(0.01)
            else:
                time.sleep(0.05)
