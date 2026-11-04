"""Set up Acuminator suppression files so the runner can write to them.

The runner's ``generate-suppressions`` / ``report-and-generate`` work modes
refuse to run unless each project already has a ``<ProjectName>.acuminator``
file next to it **and** references it as an ``<AdditionalFiles>`` item. This
module creates the empty file and adds the item when they are missing.
"""

from __future__ import annotations

import re
from pathlib import Path

EMPTY_SUPPRESSION_FILE = '<?xml version="1.0" encoding="utf-8"?>\n<suppressions>\n</suppressions>\n'

# ``Project("{GUID}") = "Name", "rel\path\Name.csproj", "{GUID}"``
_SLN_PROJECT_PATTERN = re.compile(r'^Project\("\{[^}]+\}"\)\s*=\s*"[^"]*",\s*"([^"]+\.csproj)"', re.MULTILINE)
_PROJECT_CLOSE_PATTERN = re.compile(r"[ \t]*</Project>\s*$")


def projects_in(code_source: Path) -> list[Path]:
    """The .csproj files a code source covers: itself, or every one listed in a .sln."""
    if code_source.suffix.lower() == ".csproj":
        return [code_source]
    text = code_source.read_text(encoding="utf-8-sig")
    return [code_source.parent / rel.replace("\\", "/") for rel in _SLN_PROJECT_PATTERN.findall(text)]


def _references_additional_file(csproj_text: str, file_name: str) -> bool:
    pattern = re.compile(r"<AdditionalFiles\s+Include\s*=\s*\"([^\"]+)\"", re.IGNORECASE)
    return any(Path(m).name.lower() == file_name.lower() for m in pattern.findall(csproj_text))


def ensure_suppression_setup(code_source: Path) -> tuple[list[Path], list[Path]]:
    """Make every project under ``code_source`` ready for suppression generation.

    Returns ``(suppression_files, modified_project_files)``.
    """
    suppression_files: list[Path] = []
    modified: list[Path] = []
    for csproj in projects_in(code_source):
        suppression = csproj.with_suffix(".acuminator")
        suppression_files.append(suppression)
        if not suppression.exists():
            suppression.write_text(EMPTY_SUPPRESSION_FILE, encoding="utf-8")

        raw = csproj.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        if _references_additional_file(text, suppression.name):
            continue
        close = _PROJECT_CLOSE_PATTERN.search(text)
        if close is None:
            raise RuntimeError(f"Cannot add AdditionalFiles item: no </Project> element in {csproj}")
        newline = "\r\n" if "\r\n" in text else "\n"
        item_group = newline.join(
            ["  <ItemGroup>", f'    <AdditionalFiles Include="{suppression.name}" />', "  </ItemGroup>", ""]
        )
        updated = text[: close.start()] + item_group + text[close.start() :]
        csproj.write_text(updated, encoding="utf-8-sig" if has_bom else "utf-8", newline="")
        modified.append(csproj)
    return suppression_files, modified
