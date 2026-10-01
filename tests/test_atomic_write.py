"""State files (citizen reports, analyst feedback, the Level-2 seeds) are rewritten whole; a crash
in the middle of a plain `write_text` left half a file -- a corrupt store on a public server.
`write_text_atomic` writes a temp file in the same directory and `os.replace`s it (QA N5)."""

from __future__ import annotations

import os

import pytest

from qorgan.atomic import write_text_atomic


def test_writes_the_whole_text(tmp_path):
    path = tmp_path / "sub" / "state.jsonl"
    write_text_atomic(path, "a\nb\n")
    assert path.read_text(encoding="utf-8") == "a\nb\n"


def test_a_failure_leaves_the_old_file_intact_and_no_temp_behind(tmp_path, monkeypatch):
    path = tmp_path / "state.jsonl"
    path.write_text("old\n", encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_text_atomic(path, "new\n")
    assert path.read_text(encoding="utf-8") == "old\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.jsonl"]


def test_the_reports_store_rewrites_atomically(tmp_path, monkeypatch):
    from qorgan.reports import store

    calls = []
    monkeypatch.setattr(store, "write_text_atomic", lambda path, text: calls.append(path))
    store._rewrite([], tmp_path / "citizen_reports.jsonl")
    assert calls == [tmp_path / "citizen_reports.jsonl"]
