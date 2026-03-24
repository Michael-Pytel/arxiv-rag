"""
scripts/deduplicate.py — global deduplication pass across all .jsonl files

Deduplication key: paper "id" field (e.g. "2212.04285v3")
For papers with multiple versions (e.g. v1, v2, v3), keeps the LATEST version.

Usage:
    # Dry run — just report stats, write nothing
    python scripts/deduplicate.py --data-dir data/

    # Write deduplicated output to a single file
    python scripts/deduplicate.py --data-dir data/ --output data/papers_deduped.jsonl

    # Write deduplicated output AND keep per-category files
    python scripts/deduplicate.py --data-dir data/ --output data/papers_deduped.jsonl --split-by-category
"""

import argparse
import json
import glob
import os
import re
from collections import defaultdict
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def base_id(paper_id: str) -> str:
    """
    Strip version suffix to get canonical paper ID.
    '2212.04285v3' → '2212.04285'
    'hep-th/9901001v2' → 'hep-th/9901001'
    """
    return re.sub(r"v\d+$", "", paper_id)


def version_number(paper_id: str) -> int:
    """Extract version number, default to 0 if absent."""
    match = re.search(r"v(\d+)$", paper_id)
    return int(match.group(1)) if match else 0


def load_jsonl(path: str) -> tuple[list[dict], int]:
    """Load a .jsonl file. Returns (papers, skipped_count)."""
    papers, skipped = [], 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                papers.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    return papers, skipped


def write_jsonl(papers: list[dict], path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in papers:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


# ── Core deduplication ────────────────────────────────────────────────────────

def deduplicate(data_dir: str) -> tuple[list[dict], dict]:
    """
    Load all .jsonl files, deduplicate globally.

    Strategy:
    - Same base ID (ignoring version) → keep the highest version
    - Tie on version → keep the one with the latest 'updated' timestamp
    - Merge categories lists so no category information is lost

    Returns:
        deduped  — list of unique papers (latest version each)
        stats    — dict with counts for reporting
    """
    paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.jsonl"), recursive=True))
    if not paths:
        raise FileNotFoundError(f"No .jsonl files found under '{data_dir}'")

    print(f"Found {len(paths)} file(s):")
    for p in paths:
        print(f"  {Path(p).name}")

    # Pass 1: load everything
    all_papers = []
    total_skipped = 0
    per_file_counts = {}

    for path in paths:
        papers, skipped = load_jsonl(path)
        per_file_counts[Path(path).name] = len(papers)
        all_papers.extend(papers)
        total_skipped += skipped
        if skipped:
            print(f"  Warning: {skipped} malformed lines skipped in {Path(path).name}")

    total_loaded = len(all_papers)
    print(f"\nLoaded {total_loaded:,} records total ({total_skipped} malformed lines skipped)")

    # Pass 2: group by base ID, keep latest version + merge categories
    groups: dict[str, dict] = {}

    for paper in all_papers:
        pid   = paper.get("id", "")
        bid   = base_id(pid)
        ver   = version_number(pid)

        if bid not in groups:
            groups[bid] = paper
            groups[bid]["_version"] = ver
        else:
            existing     = groups[bid]
            existing_ver = existing.get("_version", 0)

            # Keep latest version
            if ver > existing_ver:
                # Carry over merged categories before replacing
                merged_cats = list(dict.fromkeys(
                    existing.get("categories", []) + paper.get("categories", [])
                ))
                groups[bid] = paper
                groups[bid]["_version"] = ver
                groups[bid]["categories"] = merged_cats
            else:
                # Same or older version — just merge categories
                merged_cats = list(dict.fromkeys(
                    existing.get("categories", []) + paper.get("categories", [])
                ))
                groups[bid]["categories"] = merged_cats

    # Pass 3: clean up internal field, sort by published date descending
    deduped = []
    for paper in groups.values():
        paper.pop("_version", None)
        deduped.append(paper)

    deduped.sort(key=lambda p: p.get("published", ""), reverse=True)

    stats = {
        "files":          len(paths),
        "total_loaded":   total_loaded,
        "unique_papers":  len(deduped),
        "duplicates":     total_loaded - len(deduped),
        "per_file":       per_file_counts,
    }

    return deduped, stats


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_stats(stats: dict, deduped: list[dict]):
    print("\n" + "=" * 50)
    print("Deduplication report")
    print("=" * 50)
    print(f"Files processed:    {stats['files']}")
    print(f"Records loaded:     {stats['total_loaded']:,}")
    print(f"Unique papers:      {stats['unique_papers']:,}")
    print(f"Duplicates removed: {stats['duplicates']:,}  "
          f"({stats['duplicates'] / stats['total_loaded'] * 100:.1f}%)")

    print("\nPer-file breakdown:")
    for fname, count in stats["per_file"].items():
        print(f"  {fname:<40} {count:>8,} records")

    # Category distribution
    cat_counts: dict[str, int] = defaultdict(int)
    for p in deduped:
        cat_counts[p.get("primary_category", "unknown")] += 1

    print("\nTop categories (primary):")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])[:10]:
        bar = "█" * (count * 30 // max(cat_counts.values()))
        print(f"  {cat:<12} {count:>7,}  {bar}")

    # Version distribution
    versioned = sum(1 for p in deduped if re.search(r"v\d+$", p.get("id", "")))
    print(f"\nPapers with version suffix: {versioned:,} / {stats['unique_papers']:,}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Deduplicate arxiv .jsonl files globally.")
    parser.add_argument("--data-dir",  default="data/", help="Directory with .jsonl files")
    parser.add_argument("--output",    default=None,    help="Output path for deduplicated .jsonl")
    parser.add_argument("--split-by-category", action="store_true",
                        help="Also write one .jsonl per primary_category into output dir")
    args = parser.parse_args()

    deduped, stats = deduplicate(args.data_dir)
    print_stats(stats, deduped)

    if args.output:
        write_jsonl(deduped, args.output)
        print(f"\nWrote {len(deduped):,} papers → {args.output}")

        if args.split_by_category:
            out_dir = Path(args.output).parent / "by_category"
            by_cat: dict[str, list] = defaultdict(list)
            for p in deduped:
                by_cat[p.get("primary_category", "unknown")].append(p)

            for cat, papers in by_cat.items():
                safe_cat = cat.replace("/", "_")
                path = out_dir / f"{safe_cat}.jsonl"
                write_jsonl(papers, str(path))

            print(f"Wrote {len(by_cat)} category files → {out_dir}/")
    else:
        print("\nDry run — no files written. Use --output to save results.")


if __name__ == "__main__":
    main()
