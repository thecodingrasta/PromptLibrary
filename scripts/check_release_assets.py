"""Check local documentation links, version consistency and required public assets."""

import ast
import re
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "LICENSE",
    "NOTICE",
    "AGENTS.md",
    ".env.example",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/ci.yml",
    "docs/mcp-tools.md",
    "scripts/package_smoke.py",
    "scripts/docker_smoke.py",
]


def main() -> None:
    errors: list[str] = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append("Missing: " + name)
    files = list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))
    for file in files:
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", file.read_text()):
            target = match[1].split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (file.parent / unquote(target)).exists():
                errors.append(f"Broken link in {file.name}: {target}")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    module = ast.parse((ROOT / "src/promptlibrary/__init__.py").read_text())
    version = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    )
    if version != metadata["project"]["version"]:
        errors.append("Package and runtime versions differ.")
    for name in [".env", "_launchPack", "MISSION.md", ".coverage"]:
        if (ROOT / name).exists():
            errors.append("Remove private or generated release asset: " + name)
    if errors:
        raise SystemExit("\n".join(errors))
    print("Required assets, local links and version consistency passed.")


if __name__ == "__main__":
    main()
