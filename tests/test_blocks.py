"""`_blocks` edits hand-maintained TOML/YAML without touching anything of the
owner's — comments, ordering and unrelated entries must survive byte-for-byte."""
import re

import pytest

from llm_wiki_base import _blocks

KEY = "mcp_servers"
NAME = "llm-wiki-base-mcp"
ENTRY = {"command": "llm-wiki-base", "args": ["serve", "--mcp"], "cwd": "/Users/me/.llm-wiki-base"}


# ── TOML (codex) ────────────────────────────────────────────────────────────

def test_toml_upsert_into_empty_file():
    out = _blocks.upsert("toml", "", KEY, NAME, ENTRY)
    assert f"[{KEY}.{NAME}]" in out
    assert 'command = "llm-wiki-base"' in out
    assert 'args = ["serve", "--mcp"]' in out
    _blocks.validate("toml", out)


def test_toml_keeps_the_owners_comments_and_tables():
    before = ('# my codex settings\n'
              'model = "gpt-5"\n\n'
              '[mcp_servers.context7]\n'
              'command = "npx"   # mine\n'
              'args = ["-y", "ctx7"]\n')
    out = _blocks.upsert("toml", before, KEY, NAME, ENTRY)
    assert out.startswith(before)                       # nothing above was touched
    _blocks.validate("toml", out)
    assert _blocks.names("toml", out, KEY) == ["context7", NAME]


def test_toml_upsert_is_idempotent_and_updates_in_place():
    once = _blocks.upsert("toml", "", KEY, NAME, ENTRY)
    moved = {**ENTRY, "cwd": "/elsewhere"}
    twice = _blocks.upsert("toml", once, KEY, NAME, moved)
    assert _blocks.block_names(twice) == [NAME]         # replaced, not duplicated
    assert twice.count(f"[{KEY}.{NAME}]") == 1
    assert 'cwd = "/elsewhere"' in twice and "/Users/me" not in twice
    _blocks.validate("toml", twice)


def test_toml_two_servers_get_two_blocks():
    out = _blocks.upsert("toml", "", KEY, NAME, ENTRY)
    out = _blocks.upsert("toml", out, KEY, "other", ENTRY)
    assert _blocks.block_names(out) == [NAME, "other"]
    assert out.count(_blocks.BLOCK_BEGIN) == 2
    _blocks.validate("toml", out)


def test_toml_entry_of_reads_back_what_we_wrote():
    out = _blocks.upsert("toml", "", KEY, NAME, ENTRY)
    assert _blocks.entry_of("toml", out, KEY, NAME) == ENTRY


def test_toml_env_subtable():
    out = _blocks.upsert("toml", "", KEY, NAME, {**ENTRY, "env": {"WIKI": "docs"}})
    assert f"[{KEY}.{NAME}.env]" in out and 'WIKI = "docs"' in out
    _blocks.validate("toml", out)


def test_toml_drops_our_block():
    out = _blocks.upsert("toml", "# a\nb = 1\n", KEY, NAME, ENTRY)
    back = _blocks.drop("toml", out, KEY, NAME)
    assert _blocks.BLOCK_BEGIN not in back and NAME not in back
    assert "# a" in back and "b = 1" in back


def test_removing_a_block_leaves_no_pile_of_blank_lines():
    out = _blocks.upsert("toml", "# a\nb = 1\n", KEY, NAME, ENTRY)
    back = _blocks.drop("toml", out, KEY, NAME)
    assert back == "# a\nb = 1\n"                  # exactly the file we started with


def test_toml_drops_a_hand_written_table():
    text = ('[mcp_servers.other]\ncommand = "x"\n\n'
            f'[{KEY}.{NAME}]\ncommand = "llm-wiki-base"\nargs = ["serve", "--mcp"]\n\n'
            '[mcp_servers.keepme]\ncommand = "y"\n')
    out = _blocks.drop("toml", text, KEY, NAME)
    assert NAME not in out
    assert "keepme" in out and "other" in out
    _blocks.validate("toml", out)


def test_toml_refuses_to_extend_an_inline_table():
    with pytest.raises(ValueError, match="inline table"):
        _blocks.upsert("toml", f"{KEY} = {{ foo = {{ command = 'x' }} }}\n", KEY, NAME, ENTRY)


def test_validate_reports_broken_toml():
    with pytest.raises(ValueError, match="TOML"):
        _blocks.validate("toml", "[mcp_servers\nbroken")


# ── YAML (hermes) ───────────────────────────────────────────────────────────

def test_yaml_creates_the_mapping_when_absent():
    out = _blocks.upsert("yaml", "# hermes config\nprofile: default\n", KEY, NAME, ENTRY)
    assert f"{KEY}:" in out
    assert "  llm-wiki-base-mcp:" in out
    assert "command: " in out
    _blocks.validate("yaml", out)


def test_yaml_inserts_into_the_owners_existing_mapping():
    before = (f"{KEY}:\n"
              "  context7:\n"
              "    command: npx\n"
              "    args: [\"-y\", \"ctx7\"]\n")
    out = _blocks.upsert("yaml", before, KEY, NAME, ENTRY)
    assert out.count(f"{KEY}:") == 1                    # no duplicate top-level key
    _blocks.validate("yaml", out)
    assert _blocks.names("yaml", out, KEY) == ["context7", NAME]
    assert "command: npx" in out                        # owner's entry untouched


def test_yaml_matches_the_files_indentation():
    before = f"{KEY}:\n    context7:\n        command: npx\n"
    out = _blocks.upsert("yaml", before, KEY, NAME, ENTRY)
    assert "    llm-wiki-base-mcp:" in out              # 4-space like the owner's
    assert "        command: " in out                   # fields one level deeper
    assert not re.search(rf"^  {NAME}:", out, re.MULTILINE)   # not our default 2
    assert out.index("context7") < out.index(NAME)      # owner's entries stay first
    _blocks.validate("yaml", out)


def test_yaml_upsert_is_idempotent():
    once = _blocks.upsert("yaml", "", KEY, NAME, ENTRY)
    twice = _blocks.upsert("yaml", once, KEY, NAME, {**ENTRY, "cwd": "/x"})
    assert _blocks.block_names(twice) == [NAME]
    assert twice.count(f"{NAME}:") == 1
    assert "/x" in twice


def test_yaml_drops_only_our_entry():
    text = (f"{KEY}:\n"
            "  context7:\n"
            "    command: npx\n"
            "    args: [\"-y\", \"ctx7\"]\n"
            "  keepme:\n"
            "    command: y\n")
    ours = _blocks.upsert("yaml", text, KEY, NAME, ENTRY)
    back = _blocks.drop("yaml", ours, KEY, NAME)
    assert NAME not in back
    assert "context7" in back and "keepme" in back and "args" in back
    _blocks.validate("yaml", back)


def test_yaml_drops_a_hand_written_entry():
    text = (f"{KEY}:\n"
            f"  {NAME}:\n"
            "    command: llm-wiki-base\n"
            "    args: [\"serve\", \"--mcp\"]\n"
            "  keepme:\n"
            "    command: y\n")
    out = _blocks.drop("yaml", text, KEY, NAME)
    assert NAME not in out and "keepme" in out and "command: y" in out
    assert "command: llm-wiki-base" not in out


def test_yaml_refuses_a_result_with_duplicate_top_level_keys():
    # `mcp_servers: {inline}` is invisible to the mapping-line probe, so an
    # appended header would duplicate the key — validate must catch it.
    with pytest.raises(ValueError, match="trùng ở top-level"):
        _blocks.validate("yaml", f"{KEY}: {{a: 1}}\n{KEY}:\n  x:\n    command: y\n")


def test_yaml_refuses_tab_indentation():
    with pytest.raises(ValueError, match="tab"):
        _blocks.validate("yaml", f"{KEY}:\n\t{NAME}:\n\t  command: x\n")
