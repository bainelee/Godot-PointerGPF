import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQ_DIR = ROOT / "docs" / "authoritative-requirements"
OUT_FILE = REQ_DIR / "requirements-index.json"

INPUT_FILES = {
    "product_requirements": REQ_DIR / "01-actual-product-requirements.md",
    "experience_requirements": REQ_DIR / "02-user-experience-requirements.md",
    "scenario_cases": REQ_DIR / "03-real-world-scenarios-and-case-studies.md",
}


SECTION_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
FIELD_RE = re.compile(r"^- ([^：:]+)[：:]\s*(.*)$")
SUB_BULLET_RE = re.compile(r"^\s{2,}-\s+(.*)$")


def _parse_sections(markdown: str) -> list[dict[str, Any]]:
    matches = list(SECTION_RE.finditer(markdown))
    sections: list[dict[str, Any]] = []

    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip("\n")
        fields = _parse_fields(body)
        sections.append({"title": title, "fields": fields})
    return sections


def _parse_fields(body: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    current_key: str | None = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        m_field = FIELD_RE.match(line)
        if m_field:
            key = m_field.group(1).strip()
            value = m_field.group(2).strip()
            current_key = key
            if value:
                fields[key] = value
            else:
                fields[key] = []
            continue

        m_sub = SUB_BULLET_RE.match(line)
        if m_sub and current_key is not None:
            item = m_sub.group(1).strip()
            if not isinstance(fields.get(current_key), list):
                fields[current_key] = [str(fields[current_key])]
            fields[current_key].append(item)

    return fields


def _load_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def generate() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(REQ_DIR.relative_to(ROOT)).replace("\\", "/"),
        "source_files": {k: str(v.relative_to(ROOT)).replace("\\", "/") for k, v in INPUT_FILES.items()},
        "items": {},
    }

    for key, path in INPUT_FILES.items():
        markdown = _load_markdown(path)
        payload["items"][key] = _parse_sections(markdown)

    return payload


def main() -> int:
    payload = generate()
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] requirements index generated: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
