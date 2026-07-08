"""Pipeline plan-JSON extraction tests (Phase 4 / Global rule: robust parsing)."""
from __future__ import annotations

import pytest

from app.services.pipeline import check_command, extract_json, parse_coder


def test_plain_object():
    assert extract_json('{"steps":[{"id":1}]}') == {"steps": [{"id": 1}]}


def test_fenced_json():
    text = 'Here is the plan:\n```json\n{"steps":[{"id":1,"title":"x"}]}\n```\nDone.'
    assert extract_json(text)["steps"][0]["title"] == "x"


def test_prose_wrapped_object():
    text = 'Sure! {"steps":[{"id":1,"kind":"code"}]} hope that helps'
    assert extract_json(text)["steps"][0]["kind"] == "code"


def test_nested_braces_and_strings():
    text = '{"steps":[{"detail":"use {curly} and \\"quotes\\"","id":2}]}'
    got = extract_json(text)
    assert got["steps"][0]["id"] == 2
    assert "{curly}" in got["steps"][0]["detail"]


def test_array_top_level():
    assert extract_json('[{"id":1},{"id":2}]') == [{"id": 1}, {"id": 2}]


def test_invalid_raises():
    with pytest.raises(ValueError):
        extract_json("no json here at all")


def test_check_command_dotnet(tmp_path):
    (tmp_path / "app.csproj").write_text("<Project/>", encoding="utf-8")
    assert check_command(tmp_path) == ["dotnet", "build"]


def test_check_command_node_requires_build_script(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts":{}}', encoding="utf-8")
    assert check_command(tmp_path) is None
    (tmp_path / "package.json").write_text(
        '{"scripts":{"build":"vite build"}}', encoding="utf-8"
    )
    assert check_command(tmp_path) == ["npm", "run", "build"]


def test_check_command_none(tmp_path):
    assert check_command(tmp_path) is None


# --- coder output parsing (tolerant of weak local models) --------------------
def test_parse_coder_json():
    text = '{"files":[{"path":"a.cs","content":"x"}],"commands":[["dotnet","build"]]}'
    files, cmds = parse_coder(text, [])
    assert files[0]["path"] == "a.cs"
    assert cmds == [["dotnet", "build"]]


def test_parse_coder_file_markers():
    text = "FILE: Program.cs\n```csharp\nConsole.WriteLine(1);\n```\n"
    files, cmds = parse_coder(text, [])
    assert files[0]["path"] == "Program.cs"
    assert "Console.WriteLine" in files[0]["content"]


def test_parse_coder_bare_block_maps_to_single_target():
    text = "Here you go:\n```csharp\nclass P {}\n```"
    files, _ = parse_coder(text, ["Program.cs"])
    assert files[0]["path"] == "Program.cs"
    assert "class P" in files[0]["content"]


def test_parse_coder_bare_blocks_zip_multiple_targets():
    text = "```cs\nA\n```\n```cs\nB\n```"
    files, _ = parse_coder(text, ["a.cs", "b.cs"])
    assert [f["path"] for f in files] == ["a.cs", "b.cs"]
    assert files[1]["content"].strip() == "B"


def test_parse_coder_strips_markdown_decorated_path():
    # Model wrote FILE: **Program.cs** — the ** must be stripped from the path.
    text = "FILE: **Program.cs**\n```csharp\nclass P {}\n```"
    files, _ = parse_coder(text, [])
    assert files[0]["path"] == "Program.cs"


def test_parse_coder_json_with_code_content_falls_back():
    # JSON with real code inside breaks json.loads -> falls back to code block.
    text = '{"files":[{"path":"P.cs","content":"line1\nline2 "quoted""}]}\n```cs\nreal\n```'
    files, _ = parse_coder(text, ["P.cs"])
    assert files and "real" in files[0]["content"]
