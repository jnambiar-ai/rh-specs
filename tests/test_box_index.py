import ast
import csv
import importlib.util
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "box_drive_index.py"
spec = importlib.util.spec_from_file_location("box_drive_index", SCRIPT)
bdi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bdi)


def build_tree(root: Path):
    (root / "Sofas" / "prod12345678").mkdir(parents=True)
    (root / "Sofas" / "prod12345678" / "tp_prod12345678_front.jpg").write_bytes(b"xx")
    (root / "Sofas" / "prod12345678" / "model.obj").write_bytes(b"yyy")
    (root / "Swatches").mkdir()
    (root / "Swatches" / "linen.png").write_bytes(b"z")
    (root / "readme.txt").write_text("hi")


def test_index_rows_and_no_modification(tmp_path):
    box = tmp_path / "Box"
    build_tree(box)
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in box.rglob("*")}
    out = tmp_path / "out" / "idx.csv"
    assert bdi.main([str(box), "--out", str(out)]) == 0
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in box.rglob("*")}
    assert before == after  # nothing under the scanned folder changed
    rows = {r["file_name"]: r for r in csv.DictReader(out.open())}
    assert rows["tp_prod12345678_front.jpg"]["prod_ids"] == "prod12345678"
    assert rows["tp_prod12345678_front.jpg"]["class_guess"] == "product shot"
    assert rows["model.obj"]["class_guess"] == "3D model"
    assert rows["linen.png"]["class_guess"] == "swatch"
    assert rows["readme.txt"]["class_guess"] == "other"
    assert rows["readme.txt"]["folder_path"] == ""


def test_refuses_output_inside_scanned_folder(tmp_path):
    box = tmp_path / "Box"
    build_tree(box)
    assert bdi.main([str(box), "--out", str(box / "idx.csv")]) == 2
    assert not (box / "idx.csv").exists()


def test_symlinks_not_followed(tmp_path):
    box = tmp_path / "Box"
    build_tree(box)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    os.symlink(outside, box / "link")
    out = tmp_path / "idx.csv"
    bdi.main([str(box), "--out", str(out)])
    assert "secret.txt" not in out.read_text()


FORBIDDEN_ATTRS = {
    "remove", "unlink", "rename", "replace", "rmdir", "removedirs", "rmtree", "move", "copy", "copy2",
    "copytree", "chmod", "chown", "utime", "write_text", "write_bytes", "read_text", "read_bytes",
    "truncate", "symlink_to", "hardlink_to", "touch", "system", "popen", "run", "call", "Popen",
}


def test_script_source_has_no_write_or_read_of_box_files():
    tree = ast.parse(SCRIPT.read_text())
    names, opens = set(), 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                names.add(f.attr)
                if f.attr == "open":
                    opens += 1
            elif isinstance(f, ast.Name):
                names.add(f.id)
                if f.id == "open":
                    opens += 1
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) else [])
            assert not {"shutil", "subprocess"} & {m.split(".")[0] for m in mods if m}
    assert not (FORBIDDEN_ATTRS & names), FORBIDDEN_ATTRS & names
    assert opens == 1  # exactly one open(): the output csv
    assert 'out.open("w"' in SCRIPT.read_text()
