#!/usr/bin/env python3
"""Create and run bounded, package-free .NET concurrency labs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "lab-template"
DATA_DIR_NAME = ".csharp-concurrency-learning"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{0,95}$")
TFM_PATTERN = re.compile(r"^net(?P<major>\d+)\.0$")
MAX_OUTPUT_CHARS = 20_000


class LabError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def request_json() -> dict[str, Any]:
    try:
        value = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise LabError("invalid_json", f"Invalid JSON input: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise LabError("invalid_request", "Input must be one JSON object")
    return value


def resolve_lab(request: dict[str, Any], *, require_data: bool = True) -> tuple[Path, Path, Path]:
    raw_root = request.get("project_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise LabError("missing_project_root", "project_root is required")
    project_root = Path(raw_root).expanduser().resolve()
    if not project_root.is_dir():
        raise LabError("invalid_project_root", f"Project root does not exist: {project_root}")
    data_dir = (project_root / DATA_DIR_NAME).resolve()
    try:
        data_dir.relative_to(SKILL_ROOT)
    except ValueError:
        pass
    else:
        raise LabError("skill_source_forbidden", "Labs cannot be created inside the Skill source")
    if require_data and not (data_dir / "learning.db").is_file():
        raise LabError("not_initialized", "Initialize learning data before creating or running a lab")
    lab_id = request.get("lab_id")
    if not isinstance(lab_id, str) or not ID_PATTERN.fullmatch(lab_id):
        raise LabError("invalid_lab_id", "lab_id must contain lowercase letters, digits, dots, or hyphens")
    labs_root = (data_dir / "labs").resolve()
    lab_dir = (labs_root / lab_id).resolve()
    try:
        lab_dir.relative_to(labs_root)
    except ValueError as exc:
        raise LabError("path_escape", "Lab path escapes the learning directory") from exc
    return data_dir, labs_root, lab_dir


def installed_sdk_majors() -> list[int]:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise LabError("dotnet_not_found", "The dotnet executable is not available")
    try:
        completed = subprocess.run(
            [dotnet, "--list-sdks"], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LabError("dotnet_timeout", "dotnet --list-sdks timed out") from exc
    if completed.returncode != 0:
        raise LabError("dotnet_failed", completed.stderr.strip() or "Cannot list installed SDKs")
    majors = []
    for line in completed.stdout.splitlines():
        match = re.match(r"^(\d+)\.", line.strip())
        if match:
            majors.append(int(match.group(1)))
    if not majors:
        raise LabError("sdk_not_found", "No .NET SDK is installed")
    return sorted(set(majors))


def validate_tfm(value: Any) -> str:
    if value is None:
        return f"net{max(installed_sdk_majors())}.0"
    if not isinstance(value, str):
        raise LabError("invalid_target_framework", "target_framework must be a string such as net10.0")
    match = TFM_PATTERN.fullmatch(value)
    if match is None or int(match.group("major")) < 8:
        raise LabError("invalid_target_framework", "Only net8.0 or later is supported")
    if int(match.group("major")) > max(installed_sdk_majors()):
        raise LabError("sdk_not_found", f"No installed SDK can target {value}")
    return value


def command_create(request: dict[str, Any]) -> dict[str, Any]:
    _, labs_root, lab_dir = resolve_lab(request)
    objective_id = request.get("objective_id")
    if not isinstance(objective_id, str) or not ID_PATTERN.fullmatch(objective_id):
        raise LabError("invalid_objective_id", "objective_id has an invalid format")
    target_framework = validate_tfm(request.get("target_framework"))
    overwrite = request.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise LabError("invalid_overwrite", "overwrite must be true or false")
    if lab_dir.exists() and not overwrite:
        raise LabError("lab_exists", "The lab already exists; preserve learner work or explicitly authorize overwrite")
    labs_root.mkdir(parents=True, exist_ok=True)
    lab_dir.mkdir(parents=True, exist_ok=True)
    replacements = {
        "Lab.csproj.template": (
            "Lab.csproj",
            {"__TARGET_FRAMEWORK__": target_framework},
        ),
        "Program.cs.template": (
            "Program.cs",
            {"__LAB_ID__": request["lab_id"], "__OBJECTIVE_ID__": objective_id},
        ),
        "LabAssertions.cs": ("LabAssertions.cs", {}),
        "NuGet.Config": ("NuGet.Config", {}),
    }
    for source_name, (target_name, tokens) in replacements.items():
        content = (TEMPLATE_ROOT / source_name).read_text(encoding="utf-8")
        for token, replacement in tokens.items():
            content = content.replace(token, replacement)
        (lab_dir / target_name).write_text(content, encoding="utf-8", newline="\n")
    metadata = {
        "lab_id": request["lab_id"],
        "objective_id": objective_id,
        "target_framework": target_framework,
    }
    (lab_dir / ".lab.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "lab_dir": str(lab_dir),
        "program": str(lab_dir / "Program.cs"),
        "project": str(lab_dir / "Lab.csproj"),
        "target_framework": target_framework,
    }


def load_metadata(lab_dir: Path) -> dict[str, Any]:
    metadata_path = lab_dir / ".lab.json"
    if not metadata_path.is_file():
        raise LabError("invalid_lab", "Lab metadata is missing")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LabError("invalid_lab", "Lab metadata is invalid") from exc
    return metadata


def limits(request: dict[str, Any]) -> tuple[str, int]:
    configuration = request.get("configuration", "Debug")
    if configuration not in {"Debug", "Release"}:
        raise LabError("invalid_configuration", "configuration must be Debug or Release")
    timeout = request.get("timeout_seconds", 10)
    if not isinstance(timeout, int) or not 1 <= timeout <= 60:
        raise LabError("invalid_timeout", "timeout_seconds must be an integer from 1 to 60")
    return configuration, timeout


def execute(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
        timed_out = False
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
    duration_ms = round((time.monotonic() - started) * 1000)
    return {
        "success": not timed_out and exit_code == 0,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout": stdout[-MAX_OUTPUT_CHARS:],
        "stderr": stderr[-MAX_OUTPUT_CHARS:],
        "output_truncated": len(stdout) > MAX_OUTPUT_CHARS or len(stderr) > MAX_OUTPUT_CHARS,
    }


def command_build(request: dict[str, Any]) -> dict[str, Any]:
    _, _, lab_dir = resolve_lab(request)
    metadata = load_metadata(lab_dir)
    configuration, timeout = limits(request)
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise LabError("dotnet_not_found", "The dotnet executable is not available")
    result = execute(
        [dotnet, "build", "Lab.csproj", "--configuration", configuration, "--nologo", "-p:RestoreIgnoreFailedSources=true"],
        lab_dir,
        timeout,
    )
    return {"ok": True, "command": "build", "lab_id": metadata["lab_id"], **result}


def lab_dll(lab_dir: Path, metadata: dict[str, Any], configuration: str) -> Path:
    dll = lab_dir / "bin" / configuration / metadata["target_framework"] / "Lab.dll"
    if not dll.is_file():
        raise LabError("lab_not_built", "Build the lab successfully before running it")
    return dll


def run_arguments(request: dict[str, Any]) -> list[str]:
    arguments = request.get("arguments", [])
    if not isinstance(arguments, list) or len(arguments) > 20 or not all(isinstance(item, str) and len(item) <= 200 for item in arguments):
        raise LabError("invalid_arguments", "arguments must be a list of at most 20 short strings")
    return arguments


def command_run(request: dict[str, Any]) -> dict[str, Any]:
    _, _, lab_dir = resolve_lab(request)
    metadata = load_metadata(lab_dir)
    configuration, timeout = limits(request)
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise LabError("dotnet_not_found", "The dotnet executable is not available")
    result = execute([dotnet, str(lab_dll(lab_dir, metadata, configuration)), *run_arguments(request)], lab_dir, timeout)
    return {"ok": True, "command": "run", "lab_id": metadata["lab_id"], **result}


def command_repeat(request: dict[str, Any]) -> dict[str, Any]:
    _, _, lab_dir = resolve_lab(request)
    metadata = load_metadata(lab_dir)
    configuration, timeout = limits(request)
    repetitions = request.get("repetitions", 10)
    if not isinstance(repetitions, int) or not 1 <= repetitions <= 100:
        raise LabError("invalid_repetitions", "repetitions must be an integer from 1 to 100")
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise LabError("dotnet_not_found", "The dotnet executable is not available")
    dll = lab_dll(lab_dir, metadata, configuration)
    arguments = run_arguments(request)
    results = []
    for index in range(repetitions):
        result = execute([dotnet, str(dll), *arguments], lab_dir, timeout)
        results.append({"iteration": index + 1, **result})
        if result["timed_out"]:
            break
    return {
        "ok": True,
        "command": "repeat",
        "lab_id": metadata["lab_id"],
        "requested_repetitions": repetitions,
        "completed_repetitions": len(results),
        "successful_repetitions": sum(item["success"] for item in results),
        "timed_out": any(item["timed_out"] for item in results),
        "duration_ms": sum(item["duration_ms"] for item in results),
        "results": results,
    }


COMMANDS = {
    "create": command_create,
    "build": command_build,
    "run": command_run,
    "repeat": command_repeat,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    try:
        response = COMMANDS[args.command](request_json())
        print(json.dumps(response, ensure_ascii=False))
        return 0
    except LabError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "message": exc.message}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
