import io
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest

from pyscry import pyscry


class FakePool:
    def map(self, func: Callable[[Any], Any], iterable: Iterable[Path]) -> list[Any]:
        return [func(x) for x in iterable]


def test_process_files_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create sample source files
    f1 = tmp_path / "file1.py"
    f1.write_text("import requests\nimport missingpkg\n")
    f2 = tmp_path / "file2.py"
    f2.write_text("from os import path\n")

    # Monkeypatch PKG_MAP and md.version to control metadata lookup
    monkeypatch.setattr(pyscry, "PKG_MAP", {"requests": ["requests-pkg"]})

    class DummyMD:
        @staticmethod
        def version(dist: str) -> str:
            if dist == "requests-pkg":
                return "1.2.3"
            raise pyscry.md.PackageNotFoundError(dist)

    monkeypatch.setattr(pyscry, "md", DummyMD)

    # Run process_files with FakePool and capture output
    out: io.StringIO = io.StringIO()
    pool: FakePool = FakePool()
    pyscry.process_files(pool, [f1, f2], output=out, output_format="json", pretty=True)

    out.seek(0)
    payload = json.load(out)

    # Assert distributions and unresolved structure
    assert "distributions" in payload and "unresolved" in payload
    assert payload["distributions"] == ["requests-pkg>=1.2.3"]
    assert "missingpkg" in payload["unresolved"] and payload["unresolved"]["missingpkg"] == []
    # stdlib module 'os' should not appear in unresolved
    assert "os" not in payload["unresolved"]
