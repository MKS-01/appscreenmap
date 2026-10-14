"""Package layers (docs/MONOREPO.md): a package imports only the appscreenmap.* packages its pyproject.toml depends on."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

from appscreenmap.testkit.helpers import REPO

PREFIX = "appscreenmap-"
PACKAGES = sorted(p for p in (REPO / "packages").iterdir() if (p / "pyproject.toml").is_file())


def allowed_areas(pkg: Path) -> tuple[str, set[str]]:
    project = tomllib.loads((pkg / "pyproject.toml").read_text())["project"]
    deps = {re.match(r"[\w.-]+", d).group() for d in project["dependencies"]}  # "name>=1[extra]" → name
    area = project["name"].removeprefix(PREFIX)
    return area, {area} | {d.removeprefix(PREFIX) for d in deps if d.startswith(PREFIX)}


def imported_areas(path: Path, src: Path):
    """(line, area) for every appscreenmap.<area> a module imports, resolving relative imports."""
    package = list(path.relative_to(src).parent.parts)  # ["appscreenmap", area, ...]
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets = [a.name.split(".") for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            mod = base + (node.module.split(".") if node.module else [])
            targets = [mod + [a.name] for a in node.names] if len(mod) == 1 else [mod]
        else:
            continue
        for parts in targets:
            if parts[0] == "appscreenmap":
                yield node.lineno, parts[1] if len(parts) > 1 else "(namespace root)"


@pytest.mark.parametrize("pkg", PACKAGES, ids=lambda p: p.name)
def test_package_imports_only_declared_dependencies(pkg):
    area, allowed = allowed_areas(pkg)
    src = pkg / "src"
    assert (src / "appscreenmap" / area).is_dir(), f"{pkg.name}: code belongs in src/appscreenmap/{area}/"
    assert not (src / "appscreenmap" / "__init__.py").exists(), "appscreenmap is a namespace package"
    bad = [
        f"{py.relative_to(REPO)}:{line} imports appscreenmap.{other}"
        for py in sorted(src.rglob("*.py"))
        for line, other in imported_areas(py, src)
        if other not in allowed
    ]
    assert not bad, f"add the dependency to {pkg.name}/pyproject.toml or move the code:\n" + "\n".join(bad)
