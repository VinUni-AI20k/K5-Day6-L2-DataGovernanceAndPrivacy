"""manifest.csv = provenance contract for every data folder.

Required columns: file_id, path, source, license, split, group_id, sha256
(`path` is relative to the manifest's folder).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .io import sha256_file

MANIFEST_COLUMNS = ["file_id", "path", "source", "license", "split", "group_id", "sha256"]


def build_manifest(
    root: str | Path,
    files: list[str | Path],
    source: str,
    license: str,
    split: str | dict = "na",
    group_id: str | dict = "na",
) -> pd.DataFrame:
    """Hash `files` (relative to root) into a manifest DataFrame.

    `split` / `group_id` may be a constant or a dict {relative_path: value}.
    """
    root = Path(root)
    rows = []
    for f in sorted(str(Path(x)) for x in files):
        # Store provenance fields and a content hash so later checks can detect
        # missing files or changes to the data after the manifest was created.
        rows.append(
            {
                "file_id": Path(f).stem,
                "path": f,
                "source": source,
                "license": license,
                "split": split.get(f, "na") if isinstance(split, dict) else split,
                "group_id": group_id.get(f, "na") if isinstance(group_id, dict) else group_id,
                "sha256": sha256_file(root / f),
            }
        )
    return pd.DataFrame(rows, columns=MANIFEST_COLUMNS)


def write_manifest(df: pd.DataFrame, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df[MANIFEST_COLUMNS].to_csv(p, index=False)
    return p


def verify_manifest(manifest_path: str | Path) -> list[dict]:
    """Return a list of problems (missing file / hash mismatch / bad schema). Empty = OK."""
    manifest_path = Path(manifest_path)
    root = manifest_path.parent
    df = pd.read_csv(manifest_path, dtype=str)
    problems: list[dict] = []
    missing_cols = [c for c in MANIFEST_COLUMNS if c not in df.columns]
    if missing_cols:
        return [{"problem": "schema", "detail": f"missing columns {missing_cols}"}]
    for row in df.itertuples(index=False):
        # Manifest paths are interpreted relative to the folder containing it.
        fp = root / row.path
        if not fp.exists():
            problems.append({"problem": "missing_file", "path": row.path})
            continue
        actual = sha256_file(fp)
        if actual != row.sha256:
            problems.append({"problem": "hash_mismatch", "path": row.path, "expected": row.sha256, "actual": actual})
    return problems
