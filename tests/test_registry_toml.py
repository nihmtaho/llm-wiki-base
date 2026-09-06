"""P0: registry TOML round-trip (Windows paths must survive save/load)."""


def test_save_windows_path_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(tmp_path / "registry.toml"))
    from llm_wiki_base import registry

    data = {"wikis": [{
        "name": "n",
        "id": "abc123",
        "path": r"C:\Users\me\wiki",
        "type": "personal",
        "added": "2026-09-06T00:00:00",
    }]}
    registry.save(data)
    assert registry.load() == data


def test_save_quote_and_unicode_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(tmp_path / "registry.toml"))
    from llm_wiki_base import registry

    data = {"wikis": [{
        "name": 'my "wiki"',
        "id": "abc123",
        "path": "/tmp/wiki-héllo",
        "type": "personal",
        "added": "2026-09-06T00:00:00",
    }]}
    registry.save(data)
    assert registry.load() == data
