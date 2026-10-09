"""Template-content regression guards: typed-relations contract ships.

Skill ingest phải có bước SYNTHESIS PASS (spec §7); _schema.md phải mô tả
hợp đồng `relations:` frontmatter + `## Claims` (spec §5). Cheap guards — nếu
một refactor template xóa mất contract, test fail ngay.
"""

from llm_wiki_base._package_data import read_template

INGEST_SKILL = ("skills", "wiki", "llm-wiki-base-ingest", "SKILL.md")
SCHEMA_TEMPLATE = ("templates", "agents", "_schema.md")


def test_ingest_skill_has_synthesis_pass():
    text = read_template(*INGEST_SKILL)
    assert "SYNTHESIS PASS" in text


def test_schema_template_documents_relations_and_claims():
    text = read_template(*SCHEMA_TEMPLATE)
    assert "relations:" in text
    assert "## Claims" in text
