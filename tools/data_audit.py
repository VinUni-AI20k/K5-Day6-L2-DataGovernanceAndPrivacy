"""Data & Provenance audit for a lab track (offline, no ground truth).

Checks the things the pipeline silently depends on:
  1. manifest sha256 integrity, and whether any hashed text file would break
     under a CRLF checkout (Windows `core.autocrlf=true`);
  2. schema of the track's index CSV (required columns, nulls, duplicate ids);
  3. split hygiene — one scene must not appear in both dev and eval;
  4. stratum coverage — every (camera_id, light) cell that exists in eval must
     also exist in dev, otherwise a per-stratum threshold cannot be calibrated;
  5. descriptive image statistics per camera / light, used to justify
     normalisation choices in the report.

Usage:
    python tools/data_audit.py --track t02 --out reports/data_audit_t02.md
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common.image_ops import brightness_stats, laplacian_variance, load_rgb, to_gray  # noqa: E402
from src.common.manifest import verify_manifest  # noqa: E402

TEXT_SUFFIXES = {".csv", ".txt", ".json", ".yaml", ".yml", ".md"}


def md_table(df: pd.DataFrame) -> str:
    """Minimal markdown table (avoids a `tabulate` dependency)."""
    d = df.reset_index()
    cols = [str(c) for c in d.columns]
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---:" if pd.api.types.is_numeric_dtype(d[c]) else "---" for c in d.columns) + "|"
    body = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def check_manifest(track_dir: Path) -> tuple[list[str], list[str]]:
    """Returns (findings, crlf_fragile_files)."""
    out, fragile = [], []
    man = track_dir / "manifest.csv"
    if not man.exists():
        return [f"FAIL · no manifest.csv in {track_dir}"], fragile
    problems = verify_manifest(man)
    out.append(f"{'OK  ' if not problems else 'FAIL'} · verify_manifest: "
               f"{'all hashes match' if not problems else f'{len(problems)} problem(s): {problems[:3]}'}")
    m = pd.read_csv(man)
    for row in m.itertuples():
        p = track_dir / row.path
        if p.suffix.lower() not in TEXT_SUFFIXES or not p.exists():
            continue
        raw = p.read_bytes()
        crlf = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if crlf != raw and sha256_bytes(crlf) != row.sha256:
            fragile.append(row.path)
    out.append(f"{'OK  ' if not fragile else 'WARN'} · CRLF fragility: "
               + ("no hashed text file changes under a CRLF checkout"
                  if not fragile else
                  f"{len(fragile)} hashed text file(s) would break: {fragile}"))
    return out, fragile


def check_schema(df: pd.DataFrame, required: list[str], id_col: str) -> list[str]:
    out = []
    missing = [c for c in required if c not in df.columns]
    out.append("OK   · columns present: " + ", ".join(required) if not missing
               else f"FAIL · missing columns: {missing}")
    nulls = {c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()}
    out.append("OK   · no null cells" if not nulls else f"FAIL · nulls: {nulls}")
    dup = int(df[id_col].duplicated().sum())
    out.append(f"OK   · {id_col} unique ({len(df)} rows)" if dup == 0 else f"FAIL · {dup} duplicate {id_col}")
    return out


def check_split(df: pd.DataFrame, scene_col: str) -> tuple[list[str], pd.DataFrame]:
    out = []
    per_scene = df.groupby(scene_col)["split"].nunique()
    leaked = per_scene[per_scene > 1]
    out.append(f"OK   · split is scene-disjoint ({df[scene_col].nunique()} scenes)" if leaked.empty
               else f"FAIL · {len(leaked)} scene(s) in both splits: {list(leaked.index)}")
    cross = pd.crosstab([df.camera_id, df.light], df.split)
    for sp in ("dev", "eval"):
        if sp not in cross.columns:
            cross[sp] = 0
    gap = cross[(cross["eval"] > 0) & (cross["dev"] == 0)]
    out.append("OK   · every eval stratum has dev examples" if gap.empty
               else "WARN · eval strata with NO dev example (cannot calibrate a per-stratum threshold): "
                    + ", ".join(f"{a}/{b}" for a, b in gap.index))
    waste = cross[(cross["dev"] > 0) & (cross["eval"] == 0)]
    if not waste.empty:
        out.append("WARN · dev strata never seen at eval (calibration effort wasted): "
                   + ", ".join(f"{a}/{b}" for a, b in waste.index))
    return out, cross


def image_stats(track_dir: Path, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in df.itertuples():
        img = load_rgb(track_dir / r.path)
        gray = to_gray(img)
        bs = brightness_stats(img)
        rows.append({"image_id": r.image_id, "camera_id": r.camera_id, "light": r.light, "split": r.split,
                     "lap_var": laplacian_variance(img),
                     "sat_frac": float((gray >= 250).mean()),
                     "dark_frac": float((gray <= 12).mean()),
                     "mean": float(bs["mean"]), "std": float(bs["std"])})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="t02")
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    track_dir = Path(a.input) if a.input else root / "fixtures" / "t02_raw_qc"

    lines = [f"# Data & Provenance audit — {a.track}", "",
             f"Input: `{track_dir.relative_to(root)}` · reproduce with "
             f"`python tools/data_audit.py --track {a.track}`", ""]

    man_findings, fragile = check_manifest(track_dir)
    df = pd.read_csv(track_dir / "images.csv")
    df["scene"] = df.image_id.str.rsplit("_", n=1).str[0]
    schema_findings = check_schema(df, ["image_id", "path", "camera_id", "light", "split"], "image_id")
    split_findings, cross = check_split(df, "scene")

    lines += ["## 1. Provenance", "", "```"] + man_findings + ["```", ""]
    lines += ["## 2. Schema", "", "```"] + schema_findings + ["```", ""]
    lines += ["## 3. Split", "", "```"] + split_findings + ["```", "",
              "Images per (camera, light) × split:", "", md_table(cross), ""]

    st = image_stats(track_dir, df)
    agg = (st.groupby(["camera_id", "light"])
             .agg(n=("lap_var", "size"), lap_median=("lap_var", "median"),
                  lap_p10=("lap_var", lambda s: s.quantile(.10)),
                  sat_mean=("sat_frac", "mean"), dark_mean=("dark_frac", "mean"),
                  bright_mean=("mean", "mean")).round(3))
    lines += ["## 4. Image statistics", "", md_table(agg), "",
              "`lap_median` is the per-group sharpness level a global threshold would be compared against.", ""]
    st.to_csv(root / "reports" / f"data_stats_{a.track}.csv", index=False)
    lines += [f"Per-image features written to `reports/data_stats_{a.track}.csv`.", ""]

    fails = sum(1 for x in man_findings + schema_findings + split_findings if x.startswith("FAIL"))
    warns = sum(1 for x in man_findings + schema_findings + split_findings if x.startswith("WARN"))
    lines += ["## 5. Verdict", "", f"`{fails} FAIL, {warns} WARN`", ""]

    text = "\n".join(lines)
    if a.out:
        Path(root / a.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {a.out}  ({fails} FAIL, {warns} WARN)")
    else:
        print(text)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
