"""READ-ONLY metadata index of a Box Drive folder.

What it does: walks the folder you point it at and writes ONE csv (names, folders,
sizes, dates, any prodXXXXXXXX ids found in the path, and a guessed file class).

What it never does: open, read, download, create, edit, rename, move, copy or delete
anything inside the Box folder. It never follows symlinks. The only file it writes is the
output csv, and it refuses to write that inside the folder being scanned.
tests/test_box_index.py enforces these rules by inspecting this file's source.

Usage:  python scripts/box_drive_index.py "<path to a Box folder>" [--out data/box_drive_index.csv]
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["prod_ids", "file_name", "folder_path", "extension", "size", "modified", "class_guess"]
PROD_RE = re.compile(r"(?i)(?:tp_)?(prod\d{6,10})")
MODEL_EXT = {".obj", ".fbx", ".3ds", ".max", ".skp", ".blend", ".glb", ".gltf", ".usdz", ".stp",
             ".step", ".igs", ".iges", ".c4d", ".ma", ".mb", ".zpr", ".stl"}
CAD_EXT = {".dwg", ".dxf"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".psd", ".webp", ".gif"}


def classify(rel_path: str, ext: str) -> str:
    low = rel_path.lower()
    if ext in MODEL_EXT:
        return "3D model"
    if ext in CAD_EXT or "cad" in low or "drawing" in low or "line art" in low:
        return "CAD or drawing"
    if "swatch" in low:
        return "swatch"
    if ext in IMAGE_EXT:
        if "lifestyle" in low or "room" in low or "scene" in low:
            return "lifestyle"
        return "product shot"
    return "other"


def scan(root: Path):
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
        except OSError as e:
            print(f"cannot list {folder}: {e}", file=sys.stderr)
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    rel_folder = str(Path(entry.path).parent.relative_to(root))
                    rel = f"{rel_folder}/{entry.name}"
                    ext = Path(entry.name).suffix.lower()
                    yield {
                        "prod_ids": ";".join(sorted({m.lower() for m in PROD_RE.findall(rel)})),
                        "file_name": entry.name,
                        "folder_path": "" if rel_folder == "." else rel_folder,
                        "extension": ext.lstrip("."),
                        "size": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                        "class_guess": classify(rel, ext),
                    }
            except OSError as e:
                print(f"skipped {entry.path}: {e}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", help="Box folder to index (read-only)")
    ap.add_argument("--out", default="data/box_drive_index.csv", help="csv to write (must be outside the Box folder)")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 2
    if out == root or root in out.parents:
        print(f"refusing: the output file must NOT be inside the scanned folder ({root})", file=sys.stderr)
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    classes, exts, n = Counter(), Counter(), 0
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in scan(root):
            w.writerow(row)
            classes[row["class_guess"]] += 1
            exts[row["extension"] or "(none)"] += 1
            n += 1
    print(f"indexed {n} files under {root}\nwrote {out}")
    print("by class (guessed from names/paths only):", dict(classes))
    print("top extensions:", dict(exts.most_common(10)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
