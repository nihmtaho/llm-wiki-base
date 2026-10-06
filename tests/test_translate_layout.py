"""Translation layout v0.2: mirror tree `wiki-<lang>/`, detection, check, migrate."""
import os
import sys

import pytest

from llm_wiki_base.translate import (
    migrate_translations,
    run_check,
    translation_dir_name,
)


def test_translation_dir_name():
    assert translation_dir_name("vi") == "wiki-vi"
    assert translation_dir_name("ja") == "wiki-ja"
    with pytest.raises(ValueError):
        translation_dir_name("vi/../etc")


def test_is_translated_rel():
    sys.path.insert(0, os.path.abspath("src/llm_wiki_base/base_tools"))
    import chunking

    assert chunking.is_translated("wiki-vi/tech/concept/x.md")
    assert chunking.is_translated("wiki-ja/x.md")
    assert chunking.is_translated("wiki/tech/concept/x.vi.md")   # legacy inline
    assert not chunking.is_translated("wiki/tech/concept/x.md")
    assert not chunking.is_translated("raw/foo.md")


def _page(title, heading="## Section"):
    return f"---\ntitle: {title}\ndomain: tech\nkind: concept\n---\n\n# {title}\n\n{heading}\n\nbody\n"


def _wiki(tmp_path):
    src = tmp_path / "wiki" / "tech" / "concept"
    src.mkdir(parents=True)
    (src / "a.md").write_text(_page("A"), encoding="utf-8")


def test_run_check_pass(tmp_path):
    _wiki(tmp_path)
    tgt = tmp_path / "wiki-vi" / "tech" / "concept"
    tgt.mkdir(parents=True)
    (tgt / "a.md").write_text(_page("A"), encoding="utf-8")
    assert run_check(tmp_path, "vi") == 0


def test_run_check_missing(tmp_path):
    _wiki(tmp_path)
    assert run_check(tmp_path, "vi") == 1


def test_run_check_heading_mismatch(tmp_path):
    _wiki(tmp_path)
    tgt = tmp_path / "wiki-vi" / "tech" / "concept"
    tgt.mkdir(parents=True)
    (tgt / "a.md").write_text(_page("A", heading="### Renamed"), encoding="utf-8")
    assert run_check(tmp_path, "vi") == 1


def test_run_check_orphan(tmp_path):
    _wiki(tmp_path)
    tgt = tmp_path / "wiki-vi" / "tech" / "concept"
    tgt.mkdir(parents=True)
    (tgt / "a.md").write_text(_page("A"), encoding="utf-8")
    (tgt / "gone.md").write_text(_page("Gone"), encoding="utf-8")
    assert run_check(tmp_path, "vi") == 1


def test_run_check_skips_log(tmp_path):
    _wiki(tmp_path)
    (tmp_path / "wiki" / "log.md").write_text("# log\n", encoding="utf-8")
    tgt = tmp_path / "wiki-vi" / "tech" / "concept"
    tgt.mkdir(parents=True)
    (tgt / "a.md").write_text(_page("A"), encoding="utf-8")
    assert run_check(tmp_path, "vi") == 0


def test_migrate_moves_legacy(tmp_path):
    src = tmp_path / "wiki" / "tech" / "concept"
    src.mkdir(parents=True)
    legacy = src / "a.vi.md"
    legacy.write_text(_page("A"), encoding="utf-8")
    moved = migrate_translations(tmp_path, "vi")
    assert moved == [("wiki/tech/concept/a.vi.md", "wiki-vi/tech/concept/a.md")]
    assert not legacy.exists()
    assert (tmp_path / "wiki-vi" / "tech" / "concept" / "a.md").exists()


def test_migrate_never_overwrites(tmp_path):
    src = tmp_path / "wiki" / "tech" / "concept"
    src.mkdir(parents=True)
    (src / "a.vi.md").write_text(_page("old"), encoding="utf-8")
    tgt = tmp_path / "wiki-vi" / "tech" / "concept"
    tgt.mkdir(parents=True)
    (tgt / "a.md").write_text(_page("new"), encoding="utf-8")
    assert migrate_translations(tmp_path, "vi") == []
    assert (src / "a.vi.md").exists()
    assert "new" in (tgt / "a.md").read_text(encoding="utf-8")
