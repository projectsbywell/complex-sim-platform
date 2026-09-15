# Contributing to complex-sim-platform

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Workflow](#development-workflow)
4. [Branch Naming](#branch-naming)
5. [Commit Messages](#commit-messages)
6. [Code Style](#code-style)
7. [Testing](#testing)
8. [Documentation](#documentation)
9. [Pull Request Process](#pull-request-process)
10. [Code Review Guidelines](#code-review-guidelines)
11. [Issue Tracking](#issue-tracking)

---

## Code of Conduct

We are committed to providing a welcoming and inclusive experience
for everyone. Contributions should be respectful, constructive,
and focused on the project's goals.

---

## Getting Started

### Prerequisites

- Python 3.10+
- Git 2.40+
- Docker (optional, for full deployment)
- Node.js 18+ (optional, for frontend development)

### Setup

```bash
# Fork the repository
git clone https://github.com/your-username/complex-sim-platform.git
cd complex-sim-platform

# Create development environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r pipeline/requirements.txt
pip install -e ".[dev]"

# Install dev tools
pip install pytest pytest-cov hypothesis black flake8 mypy

# Verify installation
python -c "import simcore; print(simcore.__version__)"
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Run specific test module
pytest tests/test_simcore/ -v

# Run property-based tests
pytest tests/ -k "hypothesis" -v
```

---

## Development Workflow

### Branch Strategy

We use a simplified GitFlow:
- `main` — Production-ready code
- `develop` — Integration branch
- `feature/*` — New features
- `fix/*` — Bug fixes
- `docs/*` — Documentation updates

### Creating a Feature Branch

```bash
# Update main first
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/verlet-optimizer

# Make changes, commit, push
git add .
git commit -m "feat(simcore): optimize Verlet integrator step"
git push origin feature/verlet-optimizer
```

---

## Branch Naming Convention

```
{type}/{module}/{short-description}
```

**Types:**
- `feature` — New feature or enhancement
- `fix` — Bug fix
- `docs` — Documentation only
- `refactor` — Code restructuring without behavior change
- `test` — Adding or updating tests
- `perf` — Performance improvement
- `security` — Security fix

**Examples:**
- `feature/fluid-realtime-streaming`
- `fix/verlet-energy-conservation`
- `docs/tutorial-deploy-docker`
- `perf/batch-normalization-vectorized`
- `security/jwt-token-validation`

---

## Commit Messages

Follow the Conventional Commits specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `perf`, `chore`, `ci`

**Good example:**
```
feat(simcore): add symplectic Verlet integrator with energy tracking

- Implement velocity Verlet integration
- Add energy conservation monitoring
- Add unit tests for convergence

Closes #142
```

**Bad example:**
```
fixed the verlet integrator and added some tests
```

---

## Code Style

### Python Style Guide

- **Line length**: 100 characters
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes for strings
- **Imports**: Group by type (stdlib, third-party, local)
- **Type hints**: Use where practical
- **Docstrings**: Google style

```python
# Good
from typing import List, Optional

import numpy as np

from simcore.integrator import VerletIntegrator


def compute_energy(particles: np.ndarray) -> float:
    """Compute total kinetic energy of particle system.

    Args:
        particles: Array of shape (n, 6) with position and velocity.

    Returns:
        Total kinetic energy.
    """
    velocities = particles[:, 3:]
    return float(0.5 * np.sum(velocities**2))
```

### Linting and Formatting

```bash
# Format with black
black .

# Lint with flake8
flake8 simulation-core/ backend/ pipeline/

# Type check with mypy
mypy simulation-core/ backend/ pipeline/
```

### Frontend Style (if applicable)

- TypeScript strict mode
- React hooks conventionally
- ESLint + Prettier configuration

---

## Testing

### Test Structure

```
tests/
├── test_simcore/
│   ├── test_integrator.py
│   ├── test_fluid.py
│   ├── test_contact.py
│   └── test_neural.py
├── test_pipeline/
│   ├── test_collectors.py
│   ├── test_batch.py
│   ├── test_stream.py
│   ├── test_quality.py
│   ├── test_train.py
│   └── test_infer.py
├── test_backend/
│   ├── test_api.py
│   └── test_ws.py
└── conftest.py
```

### Writing Tests

```python
import pytest
import numpy as np
from simcore.integrator import VerletIntegrator, ParticleSystem


def test_energy_conservation():
    """Verlet integrator should conserve energy over short times."""
    system = ParticleSystem(n_particles=10)
    integrator = VerletIntegrator(dt=0.001)

    initial_energy = integrator.energy(system)
    integrator.step(system, n_steps=1000)
    final_energy = integrator.energy(system)

    drift = abs(final_energy - initial_energy) / abs(initial_energy)
    assert drift < 0.01, f"Energy drift too large: {drift:.4f}"


@pytest.mark.parametrize("dt", [0.001, 0.0005, 0.0001])
def test_convergence(dt):
    """Smaller time steps should produce more accurate results."""
    system = ParticleSystem(n_particles=10)
    e1 = VerletIntegrator(dt=dt).energy(system)
    e2 = VerletIntegrator(dt=dt/2).energy(system)
    # Compare convergence rate
```

### Property-Based Testing

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(st.integers(min_value=1, max_value=10000))
@settings(max_examples=50)
def test_scalability(n_particles):
    """Particle system should handle any reasonable particle count."""
    system = ParticleSystem(n_particles=n_particles)
    integrator = VerletIntegrator(dt=0.001)
    state = integrator.step(system, n_steps=10)
    assert state.n_particles == n_particles
```

---

## Documentation

All contributions must include or update documentation:

1. **New features**: Add to `docs/modules-{name}.md`
2. **New tutorials**: Add to `docs/tutorials.md`
3. **API changes**: Update relevant module documentation
4. **Architecture changes**: Update `docs/architecture.md` and ADRs

### Documentation Format

- Markdown files in `docs/`
- English titles, Portuguese body text (pt-BR)
- Code examples must be executable
- Include type hints in code snippets

---

## Pull Request Process

### Before Opening a PR

1. Ensure all tests pass: `pytest tests/`
2. Run linters: `black . && flake8 . && mypy .`
3. Update documentation if needed
4. Ensure no merge conflicts with `develop`

### PR Template

```markdown
## Description
<!-- Brief description of changes -->

## Type
- [ ] Feature
- [ ] Bug fix
- [ ] Documentation
- [ ] Performance
- [ ] Security

## Changes
<!-- List of changed files -->

## Testing
<!-- How to verify the changes -->

## Checklist
- [ ] Tests pass
- [ ] Linters pass
- [ ] Documentation updated
- [ ] Breaking changes noted
```

### Review Process

1. **Automated checks**: CI runs tests, linting, type checking
2. **Peer review**: At least one approval required
3. **Maintainer approval**: Required for `main` branch merges
4. **CI status**: Must be green before merge

---

## Code Review Guidelines

### What to Look For

- **Correctness**: Does the code do what it claims?
- **Readability**: Is the code clear and well-structured?
- **Performance**: Are there obvious inefficiencies?
- **Security**: Are there potential vulnerabilities?
- **Tests**: Are there adequate tests for new code?
- **Documentation**: Is everything documented?

### Review Comments

- Be constructive and specific
- Reference code lines when possible
- Suggest alternatives rather than dictating
- Separate must-fix from nice-to-have suggestions
- Acknowledge good patterns

---

## Issue Tracking

### Issue Labels

- `bug` — Something is broken
- `feature` — New functionality request
- `enhancement` — Improvement to existing feature
- `documentation` — Documentation task
- `question` — Support question
- `priority:high` — Critical for progress
- `priority:medium` — Important but not urgent
- `priority:low` — Nice to have

### Reporting Issues

Include:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Platform and Python version
- Relevant error messages and stack traces
- Minimal reproduction code if applicable

---

## Release Process

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Tag release: `git tag -a v1.0.0 -m "Release v1.0.0"`
4. Push tag: `git push origin v1.0.0`
5. CI/CD builds and publishes

---

## Contact

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Direct**: @worker4 on project channels

---

## Security Contributions

All security-related changes must follow these additional guidelines:

### Security Review Process
1. **Before merge**: Run `python -m pytest tests/ -k security` and `bandit -r simulation-core/ backend/ security/`
2. **Crypto changes**: Any change to `security/crypto.py` requires peer review by at least 2 reviewers
3. **Dependency updates**: `pip audit` and `safety check` must pass before merge
4. **Secrets**: Never commit secrets, keys, or passwords. Use `.env` files only.

### Reporting Security Issues
- Follow responsible disclosure (see `docs/SECURITY.md`)
- Use `security/incident_response.py` to create tracked incidents
- Include CVSS score and remediation timeline

### Security Testing
```bash
# Run security linter
bandit -r simulation-core/ backend/ security/ -ll

# Dependency vulnerability scan
pip-audit

# Run security tests
python -m pytest tests/ -k "security or crypto or auth" -v
```

