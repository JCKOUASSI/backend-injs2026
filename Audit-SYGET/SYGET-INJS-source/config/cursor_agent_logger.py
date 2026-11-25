"""
Logger automatique des actions d'agent Cursor.

Lit les fichiers jsonl de transcripts Cursor et ecrit les evenements
dans un fichier de log du projet.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from django.conf import settings

_LOGGER_STARTED = False


def _default_transcripts_dir() -> Path:
    project_slug = str(settings.BASE_DIR).replace(":", "").replace("\\", "-").replace("/", "-")
    return Path.home() / ".cursor" / "projects" / project_slug / "agent-transcripts"


def _get_transcripts_dir() -> Path:
    raw = os.environ.get("CURSOR_AGENT_TRANSCRIPTS_DIR", "").strip()
    if raw:
        return Path(raw)
    return _default_transcripts_dir()


def _jsonl_files(transcripts_dir: Path) -> list[Path]:
    if not transcripts_dir.exists():
        return []
    return sorted(transcripts_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def _format_event(line: str, transcript_file: Path) -> str:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return f"[{transcript_file.name}] {line.strip()}"

    role = payload.get("role", "unknown")
    content = payload.get("content", "")
    event_type = payload.get("type", "message")
    ts = payload.get("timestamp", "")
    if isinstance(content, list):
        content = " ".join(str(part) for part in content)
    content = str(content).replace("\n", " ").strip()
    return f"{ts} [{transcript_file.name}] [{event_type}] [{role}] {content}"


def _tail_transcripts(transcripts_dir: Path, output_file: Path, state_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    while True:
        try:
            for transcript_file in _jsonl_files(transcripts_dir):
                file_key = str(transcript_file)
                start_offset = int(state.get(file_key, 0))
                current_size = transcript_file.stat().st_size
                if start_offset > current_size:
                    start_offset = 0

                with transcript_file.open("r", encoding="utf-8", errors="replace") as src:
                    src.seek(start_offset)
                    new_lines = src.readlines()
                    new_offset = src.tell()

                if new_lines:
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    with output_file.open("a", encoding="utf-8") as out:
                        for line in new_lines:
                            line = line.strip()
                            if not line:
                                continue
                            out.write(_format_event(line, transcript_file) + "\n")

                state[file_key] = new_offset

            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(state), encoding="utf-8")
        except OSError:
            pass
        time.sleep(3)


def maybe_start_cursor_logger() -> None:
    """Demarre le logger de transcripts Cursor si conditions remplies."""
    global _LOGGER_STARTED
    if _LOGGER_STARTED:
        return
    if not settings.DEBUG:
        return
    if os.environ.get("CURSOR_AGENT_LOGGER_ENABLED", "1") != "1":
        return
    if "runserver" not in sys.argv:
        return
    if os.environ.get("RUN_MAIN") != "true":
        return

    transcripts_dir = _get_transcripts_dir()
    output_file = Path(settings.BASE_DIR) / "logs" / "cursor-agent-actions.log"
    state_file = Path(settings.BASE_DIR) / "logs" / ".cursor-agent-actions.state.json"

    thread = threading.Thread(
        target=_tail_transcripts,
        args=(transcripts_dir, output_file, state_file),
        name="cursor-agent-logger",
        daemon=True,
    )
    thread.start()
    _LOGGER_STARTED = True
