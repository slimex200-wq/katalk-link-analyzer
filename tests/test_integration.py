import pytest
from click.testing import CliRunner
from main import cli


@pytest.fixture
def sample_chat(tmp_path):
    chat = tmp_path / "chat.txt"
    chat.write_text(
        "2026년 3월 22일 오후 4:27, 나 : https://www.python.org\n"
        "2026년 3월 22일 오후 4:30, 나 : 파이썬 공식 사이트\n",
        encoding="utf-8",
    )
    return str(chat)


def test_parse_extracts_links(sample_chat, tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["parse", sample_chat, "--db-path", db_path, "--max-links", "1"])
    assert result.exit_code == 0
    assert "추출된 링크: 1개" in result.output


def test_list_empty(tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--db-path", db_path])
    assert "저장된 링크가 없습니다" in result.output


def test_parse_then_list(sample_chat, tmp_path):
    db_path = str(tmp_path / "test.db")
    runner = CliRunner()
    runner.invoke(cli, ["parse", sample_chat, "--db-path", db_path, "--max-links", "1"])
    result = runner.invoke(cli, ["list", "--db-path", db_path])
    assert "python.org" in result.output
