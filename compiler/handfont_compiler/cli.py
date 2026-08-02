from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .pipeline import compile_project
from .template import generate_template
from .template_import import import_template


def response(success: bool, **values: Any) -> dict[str, Any]:
    return {"success": success, **values}


def validate_project(project_path: str) -> dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    project_file = root / "project.json"
    if not project_file.is_file():
        return response(False, error="project.json was not found", warnings=[])

    try:
        project = json.loads(project_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return response(False, error=f"Could not read project.json: {error}", warnings=[])

    missing = [key for key in ("schemaVersion", "familyName", "styles") if key not in project]
    if missing:
        return response(False, error=f"Missing required project fields: {', '.join(missing)}", warnings=[])

    warnings: list[str] = []
    if project.get("unitsPerEm") != 1000:
        warnings.append("The first release is designed for 1000 units per em.")
    return response(True, projectPath=str(root), warnings=warnings)


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    command = request.get("command")
    if command == "health-check":
        return response(True, compilerVersion=__version__, capabilities=["validate-project", "compile-font", "generate-template", "generate-replacement-template", "import-template"])
    if command == "validate-project":
        path = request.get("projectPath")
        if not isinstance(path, str) or not path:
            return response(False, error="projectPath must be a non-empty string", warnings=[])
        return validate_project(path)
    if command == "compile-font":
        path = request.get("projectPath")
        style_id = request.get("styleId", "regular")
        if not isinstance(path, str) or not path:
            return response(False, error="projectPath must be a non-empty string", warnings=[])
        try:
            result = compile_project(path, str(style_id), request.get("outputDirectory"))
            return response(True, **result)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            return response(False, error=str(error), warnings=[])
    if command == "generate-template":
        path = request.get("projectPath")
        if not isinstance(path, str) or not path:
            return response(False, error="projectPath must be a non-empty string", warnings=[])
        try:
            result = generate_template(path, str(request.get("styleId", "regular")), str(request.get("characters", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")), str(request.get("preset", "a4-portrait")), int(request.get("variants", 1)), bool(request.get("referenceLetters", True)))
            return response(True, **result)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            return response(False, error=str(error), warnings=[])
    if command == "generate-replacement-template":
        path = request.get("projectPath")
        glyphs = request.get("glyphs")
        if not isinstance(path, str) or not isinstance(glyphs, list):
            return response(False, error="projectPath and glyphs are required", warnings=[])
        try:
            result = generate_template(path, str(request.get("styleId", "regular")), "", str(request.get("preset", "a4-portrait")), 1, bool(request.get("referenceLetters", True)), glyphs, "replacement")
            return response(True, **result)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            return response(False, error=str(error), warnings=[])
    if command == "import-template":
        path, input_path = request.get("projectPath"), request.get("inputPath")
        if not isinstance(path, str) or not isinstance(input_path, str):
            return response(False, error="projectPath and inputPath must be strings", warnings=[])
        try:
            return response(True, **import_template(path, input_path, int(request.get("threshold", 160)), str(request.get("importMode", "standard"))))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            return response(False, error=str(error), warnings=[])
    return response(False, error=f"Unknown command: {command!r}", warnings=[])


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")
        result = dispatch(request)
    except (json.JSONDecodeError, ValueError) as error:
        result = response(False, error=str(error), warnings=[])
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
