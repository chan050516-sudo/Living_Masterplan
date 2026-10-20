"""Load CSV business tables."""

import logging
from pathlib import Path
import pandas as pd

log = logging.getLogger(__name__)


def load_business(repo_root: Path, paths: dict) -> dict:
    base = repo_root / paths["base"]
    tables = {}
    for key, rel in paths["business"].items():
        path = base / rel
        if not path.exists():
            raise FileNotFoundError(f"Business file not found: {path}")
        if path.stat().st_size == 0:
            log.warning("Business file is empty, skipping: %s", path)
            tables[key] = pd.DataFrame()
            continue
        try:
            df = pd.read_csv(path)
            tables[key] = df
            log.debug("Loaded %s: %s rows x %s cols", path.name, *df.shape)
        except pd.errors.EmptyDataError:
            log.warning("Business file has no columns, skipping: %s", path)
            tables[key] = pd.DataFrame()
        except pd.errors.ParserError as e:
            log.error("Parse error in %s: %s", path, e)
            raise
    return tables