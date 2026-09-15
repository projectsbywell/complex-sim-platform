# Examples — complex-sim-platform

Executable code snippets demonstrating key platform features.

## 1. Basic Particle Simulation

```python
from simcore.integrator import VerletIntegrator, ParticleSystem
import numpy as np

# Create particle system
system = ParticleSystem(n_particles=100)
for i in range(100):
    system.add_particle(
        position=[np.random.uniform(0, 10), np.random.uniform(0, 10)],
        velocity=[np.random.normal(0, 1), np.random.normal(0, 1)],
        mass=1.0,
    )

# Create integrator and simulate
integrator = VerletIntegrator(dt=0.001, damping=0.99)
state = integrator.step(system, n_steps=10000)

print(f"Final energy: {state.total_energy:.4f}")
print(f"Energy drift: {state.energy_drift:.6e}")
```

## 2. Real-Time Fluid Visualization

```python
from simcore.fluid import StableFluidSimulator
import numpy as np

fluid = StableFluidSimulator(resolution=128, viscosity=0.1, dt=0.016)
fluid.add_obstacle(x=64, y=64, radius=10)

# Run and save frames
for step in range(500):
    fluid.add_force(x=0, y=64, force=[1.0, 0.0], continuous=True)
    state = fluid.step()
    if step % 5 == 0:
        velocity = state.get_velocity_field()
        speed = np.sqrt(velocity[:,:,0]**2 + velocity[:,:,1]**2)
        print(f"Step {step}: max_speed={speed.max():.4f}")
```

## 3. Neural Network Training Pipeline

```python
from pipeline.collectors import SyntheticStreamCollector
from pipeline.train import PipelineTrainer, TrainingConfig
import numpy as np

# Generate data
collector = SyntheticStreamCollector(
    schema={"x1": float, "x2": float, "y": float},
    noise_scale=0.05, seed=42,
)
data = collector.collect(n=5000)

# Prepare arrays
X = np.array([[d["x1"], d["x2"]] for d in data])
y = np.array([d["y"] for d in data])

# Train model
trainer = PipelineTrainer(TrainingConfig(
    hidden_layers=(64, 32), epochs=100, learning_rate=0.001,
))
history = trainer.train(X, y)

# Predict
predictions = trainer.predict(X[:10])
print(f"Predictions: {predictions}")
```

## 4. Quality Analysis Report

```python
from pipeline.quality import QualityReport, SchemaValidator

schema = {"temperature": float, "pressure": float, "label": str}
report = QualityReport(records, schema=schema)
result = report.generate()

print(f"Quality Score: {result['quality_score']}/100")
print(f"Missing Rate: {result['missing_data']['overall_missing_rate']:.4f}")
print(f"Outliers: {result['outliers']['total_outliers']}")
print(f"Schema Validity: {result['schema_validation']['validity_rate']:.4f}")

report.save("quality_report.json")
```

## 5. Inference from Checkpoint

```python
from pipeline.infer import ModelInferencer
import numpy as np

inferencer = ModelInferencer()
inferencer.load("models/model_checkpoint.json")

# Generate test data
X_test = np.random.randn(100, 10)
predictions = inferencer.predict(X_test)
evaluation = inferencer.evaluate(X_test, y_test)

print(f"R² Score: {evaluation['r2_score']:.4f}")
print(f"RMSE: {evaluation['rmse']:.4f}")

# Export with confidence
results = inferencer.predict_with_confidence(X_test)
inferencer.export_predictions(X_test, "predictions.json")
```

## 6. Streaming Data Consumer

```python
from pipeline.stream import StreamConsumer
from pipeline.collectors import SyntheticStreamCollector
import time

# Create synthetic stream
collector = SyntheticStreamCollector(
    schema={"value": float}, seed=42,
)
source = collector.stream()

# Create consumer with 5000-item buffer
consumer = StreamConsumer()
thread = consumer.start_consumer(source)

# Process in real-time
for _ in range(100):
    batch = consumer.flush()
    if batch:
        print(f"Processed {len(batch)} records")
    time.sleep(0.1)

consumer.stop_consumer()
```

## 7. Batch Aggregation

```python
from pipeline.batch import aggregate_window, batch_statistics
import numpy as np

# Simulate 1000 records
records = [{"step": i, "value": float(np.sin(i*0.01) + np.random.normal(0, 0.1))}
           for i in range(1000)]

# Aggregate in windows of 100
aggregated = aggregate_window(records, window_size=100, agg_func="mean")
print(f"Created {len(aggregated)} windows")

# Get statistics
stats = batch_statistics(records)
print(f"Mean value: {stats['value']['mean']:.4f}")
print(f"Std value: {stats['value']['std']:.4f}")
```

## 8. Outlier Detection

```python
from pipeline.quality import OutlierDetector
import numpy as np

# Create data with outliers
normal = np.random.normal(0, 1, 1000)
outliers = np.array([10, -15, 20, -25])  # 4 outliers
data_values = np.concatenate([normal, outliers])

records = [{"value": float(v), "_record_id": i} for i, v in enumerate(data_values)]
detector = OutlierDetector(records)
report = detector.multi_field_outliers(threshold=3.0)

print(f"Total outliers detected: {report['total_outliers']}")
for field, info in report['fields'].items():
    print(f"  {field}: {info['outlier_count']} outliers")
```

## 9. Multi-Source Data Collection

```python
from pipeline.collectors import PublicAPICollector, CSVCollector, SyntheticStreamCollector
from pipeline.batch import clean_data

# Collect from multiple sources
api_collector = PublicAPICollector(base_url="https://api.example.com/data")
csv_collector = CSVCollector(filepath="data.csv")
syn_collector = SyntheticStreamCollector(schema={"x": float}, seed=42)

api_data = api_collector.collect(n=100)
csv_data = csv_collector.collect(n=500)
syn_data = syn_collector.collect(n=200)

# Combine and clean
all_data = api_data + csv_data + syn_data
cleaned = clean_data(all_data)
print(f"Total records: {len(all_data)}, Cleaned: {len(cleaned)}")
```

## 10. Complete Pipeline End-to-End

```python
from pipeline.collectors import SyntheticStreamCollector
from pipeline.batch import clean_data, normalize_data
from pipeline.stream import StreamConsumer
from pipeline.quality import QualityReport
from pipeline.train import PipelineTrainer
from pipeline.infer import ModelInferencer

# 1. Collect
collector = SyntheticStreamCollector(
    schema={"f1": float, "f2": float, "target": float}, seed=42
)
data = collector.collect(n=5000)

# 2. Clean and normalize
cleaned = clean_data(data)
normalized = normalize_data(cleaned)

# 3. Quality check
report = QualityReport(normalized)
quality = report.generate()
assert quality["quality_score"] > 70, "Quality too low"

# 4. Train
X = [[r["f1"], r["f2"]] for r in normalized]
y = [r["target"] for r in normalized]
trainer = PipelineTrainer()
history = trainer.train(np.array(X), np.array(y))
trainer.save_checkpoint("model.json")

# 5. Infer
inferencer = ModelInferencer()
inferencer.load("model.json")
preds = inferencer.predict(np.array(X[:10]))
print(f"Predictions: {preds}")
```
