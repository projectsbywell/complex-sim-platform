"""
simcore — Simulation Core Package
==================================

Multi-model simulation engine with particle, fluid, rigid-body, neural,
and biological models. All models share a common interface and can be
driven through a unified SimulationEngine facade.

Exported symbols are re-exported from submodules for convenient access.
"""

__version__ = "1.0.0"

from .base import Simulatable, Vec2, clamp, seed_rng
from .particles import ParticleSimulation
from .fluids import FluidSimulation
from .physics import PhysicsSimulation
from .neural import NeuralSimulation
from .bio import BioSimulation
from .engine import SimulationEngine
from .state import save_json, load_json, to_csv, to_json_str
from .export import export_csv, export_json, export_parquet, export_hdf5

__all__ = [
    "Simulatable",
    "Vec2",
    "clamp",
    "seed_rng",
    "ParticleSimulation",
    "FluidSimulation",
    "PhysicsSimulation",
    "NeuralSimulation",
    "BioSimulation",
    "SimulationEngine",
    "save_json",
    "load_json",
    "to_csv",
    "to_json_str",
    "export_csv",
    "export_json",
    "export_parquet",
    "export_hdf5",
]
