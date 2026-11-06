"""Register this checkout in the user's Codex config without rewriting other settings."""
import datetime
import json
import os
import sys
from pathlib import Path
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    python = root / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
    if not python.is_file():
        raise SystemExit("Create/install the repository virtual environment first")
    config = Path.home() / ".codex/config.toml"
    original = config.read_bytes()
    text = original.decode("utf-8-sig")
    current = tomllib.loads(text)
    if "kakaotalk" in current.get("mcp_servers", {}):
        raise SystemExit("kakaotalk already configured; inspect before changing it")
    command = python.as_posix()
    section = ("\n\n[mcp_servers.kakaotalk]\n"
               f"command = {json.dumps(command, ensure_ascii=False)}\n"
               'args = ["-m", "kakao_mcp"]\n'
               f"cwd = {json.dumps(root.as_posix(), ensure_ascii=False)}\n"
               'startup_timeout_sec = 20\ntool_timeout_sec = 180\nenabled = true\n'
               '[mcp_servers.kakaotalk.env]\nPYTHONUTF8 = "1"\n'
               '[mcp_servers.kakaotalk.tools.kakao_publish_board_post]\napproval_mode = "prompt"\n')
    updated = text.rstrip() + section
    parsed = tomllib.loads(updated)
    assert parsed["mcp_servers"]["kakaotalk"]["command"] == command
    without_new = dict(parsed)
    without_new["mcp_servers"] = dict(parsed["mcp_servers"])
    del without_new["mcp_servers"]["kakaotalk"]
    assert without_new == current, "Unrelated config changed"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config.with_name(f"config.toml.before-kakaotalk-{stamp}")
    with backup.open("xb") as file:
        file.write(original)
    if config.read_bytes() != original:
        raise SystemExit("Config changed concurrently; no modification made")
    temporary = config.with_name(f".config-kakaotalk-{stamp}.tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, config)
    print(json.dumps({"registered": "kakaotalk", "config": str(config), "backup": str(backup)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
