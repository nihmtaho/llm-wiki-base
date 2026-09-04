import os


def test_env_is_isolated(isolated_env):
    assert os.environ["LLM_WIKI_BASE_DIR"] == str(isolated_env["base"])
    assert os.environ["HOME"] == str(isolated_env["home"])
