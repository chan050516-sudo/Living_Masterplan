"""Load YAML configuration files."""

from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "backend" / "configs"


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_paths() -> dict:
    return _load("paths.yml")


def load_peer_benchmarks() -> dict:
    return _load("peer_benchmarks.yml")


def load_benchmarks() -> dict:
    """Deprecated alias. Use load_peer_benchmarks."""
    return load_peer_benchmarks()


def load_weights() -> dict:
    return _load("weights.yml")


def load_assumptions() -> dict:
    return _load("assumptions.yml")


def load_field_metadata() -> dict:
    return _load("field_metadata.yml")


def load_taxonomy() -> dict:
    return _load("taxonomy.yml")