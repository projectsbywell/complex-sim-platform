# Pipeline — Data Lifecycle Management

The `pipeline` package handles the full data lifecycle: collection,
batching, streaming, quality control, training, and inference.

## Structure

```
pipeline/
├── collectors.py    # Data ingestion (API, CSV, synthetic streams)
├── batch.py         # Cleaning, normalization, windowed aggregation
├── stream.py        # Real-time stream consumer with ring buffer
├── quality.py       # Schema validation, outlier detection, reporting
├── train.py         # Neural network training (MLP + Adam)
├── infer.py         # Model inference from trained checkpoints
├── model_registry.py # Model versioning and storage
├── evaluate.py      # Model evaluation metrics (R², RMSE)
├── report_generator.py # Multi-format reports (md+html+json)
└── README.md        # This file
```

## Quick Start

```python
from pipeline.collectors import SyntheticStreamCollector
from pipeline.batch import clean_data, normalize_data
from pipeline.quality import QualityReport, OutlierDetector
from pipeline.train import PipelineTrainer, TrainingConfig
from pipeline.infer import ModelInferencer

# 1. Collect
collector = SyntheticStreamCollector(schema={"x": float}, seed=42)
data = collector.collect(n=5000)

# 2. Clean & normalize
cleaned = clean_data(data)
normalized = normalize_data(cleaned)

# 3. Quality check
report = QualityReport(normalized)
quality = report.generate()
assert quality["quality_score"] > 70

# 4. Train
trainer = PipelineTrainer()
history = trainer.train(X, y)
trainer.save_checkpoint("model.json")

# 5. Infer
inferencer = ModelInferencer()
inferencer.load("model.json")
preds = inferencer.predict(X[:10])
```

## Modules

### Collectors
- `SyntheticStreamCollector`: Generate synthetic data with configurable schema and noise
- `CSVCollector`: Load data from CSV files
- `PublicAPICollector`: Fetch data from REST APIs

### Batch Processing
- `clean_data`: Fill missing values, remove duplicates
- `normalize_data`: Z-score, min-max, or robust normalization
- `aggregate_window`: Windowed aggregation (mean, sum, std)
- `batch_statistics`: Summary statistics for batches

### Stream Processing
- `StreamConsumer`: Ring-buffer based real-time consumer
- Back-pressure propagation
- Configurable buffer size

### Quality Control
- `QualityReport`: 0-100 score based on missing data, outliers, schema validity
- `SchemaValidator`: Validate data against schema definitions
- `OutlierDetector`: Z-score and IQR-based outlier detection

### Training
- `PipelineTrainer`: MLP training with Adam optimizer
- `TrainingConfig`: Network architecture, hyperparameters, early stopping
- Checkpoint saving/loading (JSON)

### Inference
- `ModelInferencer`: Load checkpoints and run predictions
- Confidence intervals
- Batch prediction with export

## Configuration

All pipeline parameters are configurable via environment variables
or `TrainingConfig` objects. See `backend/.env.example` for defaults.

## Integration

The pipeline integrates with the backend via REST API:
- `POST /api/v1/pipeline/run` — Execute full pipeline
- `GET /api/v1/pipeline/results/{id}` — Retrieve results
