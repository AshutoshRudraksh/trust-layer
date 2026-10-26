from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    role: str
    allowed_tools: List[str]
    path: Path
    body: Optional[str] = None


class SkillsLoader:
    """
    Progressive Agent Skills loader:
    1. Scans skills/<role>/SKILL.md at startup and parses YAML frontmatter only.
    2. Loads the full SKILL.md instruction body only when a role agent is activated.
    3. Produces unified diffs when user memory corrections update an agent skill.
    """

    def __init__(self, skills_root: str | Path) -> None:
        self.skills_root = Path(skills_root)
        self._catalog: Dict[str, SkillDefinition] = {}
        self.refresh_catalog()

    @staticmethod
    def _parse_frontmatter(raw_text: str) -> tuple[Dict[str, str], str]:
        lines = raw_text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}, raw_text
        meta: Dict[str, str] = {}
        end_idx = 0
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end_idx = idx
                break
            if ":" in lines[idx]:
                key, val = lines[idx].split(":", 1)
                meta[key.strip()] = val.strip()
        body = "\n".join(lines[end_idx + 1 :]).strip()
        return meta, body

    def refresh_catalog(self) -> Dict[str, SkillDefinition]:
        self._catalog.clear()
        if not self.skills_root.exists():
            return {}
        for skill_file in sorted(self.skills_root.glob("*/SKILL.md")):
            raw = skill_file.read_text(encoding="utf-8")
            meta, _ = self._parse_frontmatter(raw)
            name = meta.get("name", skill_file.parent.name)
            description = meta.get("description", "")
            role = meta.get("role", name)
            tools_raw = meta.get("allowed_tools", "")
            allowed_tools = [t.strip() for t in tools_raw.split(",") if t.strip()]
            self._catalog[name] = SkillDefinition(
                name=name,
                description=description,
                role=role,
                allowed_tools=allowed_tools,
                path=skill_file,
                body=None,
            )
        return dict(self._catalog)

    def list_frontmatter(self) -> List[SkillDefinition]:
        return list(self._catalog.values())

    def load_full_skill(self, name: str) -> SkillDefinition:
        if name not in self._catalog:
            raise KeyError(f"Skill '{name}' not found in {self.skills_root}")
        entry = self._catalog[name]
        raw = entry.path.read_text(encoding="utf-8")
        _, body = self._parse_frontmatter(raw)
        return SkillDefinition(
            name=entry.name,
            description=entry.description,
            role=entry.role,
            allowed_tools=entry.allowed_tools,
            path=entry.path,
            body=body,
        )

    def propose_skill_rule_diff(self, name: str, learned_rule: str) -> str:
        full_skill = self.load_full_skill(name)
        original_raw = full_skill.path.read_text(encoding="utf-8")
        updated_raw = original_raw.rstrip() + f"\n- Learned Rule: {learned_rule.strip()}\n"
        diff = difflib.unified_diff(
            original_raw.splitlines(keepends=True),
            updated_raw.splitlines(keepends=True),
            fromfile=f"a/skills/{name}/SKILL.md",
            tofile=f"b/skills/{name}/SKILL.md",
        )
        return "".join(diff)
