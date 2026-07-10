import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, Union
from xml.etree import ElementTree as ET


NUPKG_LIB_TARGETS = [
    "net6.0-windows7.0",
    "net8.0-windows",
    "net7.0-windows",
    "net6.0-windows",
    "net48",
    "net472",
    "net462",
    "net461",
    "net45",
    "netstandard2.0",
]

UIPATH_PACKAGE_RE = re.compile(r"\bUiPath\.[A-Za-z0-9_.]+\.Activities\b", re.I)


def scan_inputs(
    input_path: Union[Path, str],
    include_xaml: bool = True,
    include_nupkg: bool = True,
) -> dict[str, Any]:
    """Scan a source tree, nupkg folder, or mixed folder for UiPath package evidence."""
    root = Path(input_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Input path does not exist: {root}")

    inventory: dict[str, Any] = {
        "input_path": str(root),
        "projects": [],
        "package_inventory": [],
        "workflow_inventory": [],
        "xaml_references": [],
        "errors": [],
    }
    seen_packages: dict[tuple[str, str], dict[str, Any]] = {}

    def add_package(record: dict[str, Any]) -> None:
        project_name = record.get("project_name") or "(unknown)"
        package_name = record.get("package_name") or ""
        key = (project_name.lower(), package_name.lower())
        if not package_name:
            return
        if key not in seen_packages:
            record.setdefault("evidence", [])
            record.setdefault("source", "unknown")
            seen_packages[key] = record
            inventory["package_inventory"].append(record)
        else:
            existing = seen_packages[key]
            if not existing.get("version") and record.get("version"):
                existing["version"] = record["version"]
            existing_sources = set((existing.get("source") or "").split(", "))
            if record.get("source"):
                existing_sources.add(record["source"])
            existing["source"] = ", ".join(sorted(s for s in existing_sources if s))
            existing["evidence"] = sorted(
                set(existing.get("evidence", [])) | set(record.get("evidence", []))
            )

    for project_path in discover_projects(root):
        try:
            project = _scan_source_project(project_path, root, include_xaml)
            inventory["projects"].append(project["project"])
            inventory["workflow_inventory"].extend(project["workflows"])
            inventory["xaml_references"].extend(project["xaml_references"])
            for package in project["packages"]:
                add_package(package)
        except Exception as exc:  # noqa: BLE001 - collect scan errors per project
            inventory["errors"].append({"path": str(project_path), "error": str(exc)})

    if include_nupkg:
        for nupkg_path in discover_nupkgs(root):
            try:
                package = _scan_nupkg(nupkg_path, root, include_xaml)
                inventory["projects"].append(package["project"])
                inventory["workflow_inventory"].extend(package["workflows"])
                inventory["xaml_references"].extend(package["xaml_references"])
                for item in package["packages"]:
                    add_package(item)
            except Exception as exc:  # noqa: BLE001 - collect scan errors per package
                inventory["errors"].append({"path": str(nupkg_path), "error": str(exc)})

    inventory["summary"] = {
        "project_count": len(inventory["projects"]),
        "package_count": len(inventory["package_inventory"]),
        "workflow_count": len(inventory["workflow_inventory"]),
        "xaml_reference_count": len(inventory["xaml_references"]),
    }
    return inventory


def discover_projects(root_path: Union[Path, str]) -> list[Path]:
    """Find UiPath source project roots while avoiding container folders that only hold nested projects."""
    root = Path(root_path).resolve()
    candidates = sorted({path.parent.resolve() for path in root.rglob("project.json")})
    if not candidates:
        return []

    def is_ancestor(folder: Path, others: list[Path]) -> bool:
        return any(other != folder and _is_relative_to(other, folder) for other in others)

    filtered: list[Path] = []
    for candidate in candidates:
        if is_ancestor(candidate, candidates):
            subprojects = [
                other
                for other in candidates
                if other != candidate and _is_relative_to(other, candidate)
            ]
            own_xamls = [
                xaml
                for xaml in candidate.glob("*.xaml")
                if not any(_is_relative_to(xaml, subproject) for subproject in subprojects)
            ]
            if own_xamls:
                filtered.append(candidate)
        else:
            filtered.append(candidate)
    return sorted(filtered) if filtered else candidates


def discover_nupkgs(root_path: Union[Path, str]) -> list[Path]:
    return sorted(Path(root_path).resolve().rglob("*.nupkg"))


def _scan_source_project(
    project_path: Path,
    root: Path,
    include_xaml: bool,
) -> dict[str, Any]:
    project_json_path = project_path / "project.json"
    project_json = _read_json(project_json_path)
    project_name = project_json.get("name") or project_path.name
    compatibility = _detect_compatibility(project_json, "")
    relative_project_path = _relative(project_path, root)
    packages: list[dict[str, Any]] = []
    workflows: list[dict[str, Any]] = []
    xaml_refs: list[dict[str, Any]] = []

    for package_name, version in _iter_dependencies(project_json):
        packages.append(
            {
                "project_name": project_name,
                "package_name": package_name,
                "version": version,
                "source": "project.json",
                "project_compatibility": compatibility,
                "evidence": [str(_relative(project_json_path, root))],
            }
        )

    xaml_files = sorted(project_path.rglob("*.xaml")) if include_xaml else []
    for xaml_path in xaml_files:
        rel = _relative(xaml_path, root)
        workflows.append(
            {
                "project_name": project_name,
                "path": str(rel),
                "source": "source",
            }
        )
        xaml_packages = _extract_packages_from_xaml_text(
            xaml_path.read_text(encoding="utf-8", errors="ignore")
        )
        for package_name in sorted(xaml_packages):
            xaml_refs.append(
                {
                    "project_name": project_name,
                    "package_name": package_name,
                    "path": str(rel),
                }
            )
            packages.append(
                {
                    "project_name": project_name,
                    "package_name": package_name,
                    "version": "",
                    "source": "xaml",
                    "project_compatibility": compatibility,
                    "evidence": [str(rel)],
                }
            )

    project = {
        "name": project_name,
        "description": project_json.get("description", ""),
        "version": project_json.get("projectVersion", ""),
        "path": str(relative_project_path),
        "source": "source",
        "compatibility": compatibility,
        "target_framework": _project_value(project_json, "targetFramework"),
        "xaml_files": [workflow["path"] for workflow in workflows],
    }
    return {
        "project": project,
        "packages": packages,
        "workflows": workflows,
        "xaml_references": xaml_refs,
    }


def _scan_nupkg(nupkg_path: Path, root: Path, include_xaml: bool) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    workflows: list[dict[str, Any]] = []
    xaml_refs: list[dict[str, Any]] = []
    with zipfile.ZipFile(nupkg_path) as zf:
        names = zf.namelist()
        nuspec_name = next((name for name in names if name.endswith(".nuspec")), "")
        nuspec = _parse_nuspec(zf.read(nuspec_name)) if nuspec_name else {}
        lib_prefix = _nupkg_lib_prefix(names)
        project_json = {}
        if lib_prefix:
            project_entry = f"{lib_prefix}project.json"
            if project_entry in names:
                project_json = json.loads(zf.read(project_entry).decode("utf-8-sig"))

        project_name = (
            project_json.get("name")
            or nuspec.get("id")
            or nupkg_path.name.removesuffix(".nupkg")
        )
        compatibility = _detect_compatibility(project_json, lib_prefix or "")
        evidence_base = f"{_relative(nupkg_path, root)}"

        for package_name, version in _iter_dependencies(project_json):
            packages.append(
                {
                    "project_name": project_name,
                    "package_name": package_name,
                    "version": version,
                    "source": "nupkg/project.json",
                    "project_compatibility": compatibility,
                    "evidence": [f"{evidence_base}!/{lib_prefix}project.json"],
                }
            )

        for dep in nuspec.get("dependencies", []):
            packages.append(
                {
                    "project_name": project_name,
                    "package_name": dep["id"],
                    "version": dep.get("version", ""),
                    "source": "nuspec",
                    "project_compatibility": compatibility,
                    "evidence": [f"{evidence_base}!/{nuspec_name}"],
                }
            )

        if include_xaml:
            for name in sorted(n for n in names if n.endswith(".xaml")):
                workflows.append(
                    {
                        "project_name": project_name,
                        "path": f"{evidence_base}!/{name}",
                        "source": "nupkg",
                    }
                )
                text = zf.read(name).decode("utf-8", errors="ignore")
                for package_name in sorted(_extract_packages_from_xaml_text(text)):
                    xaml_refs.append(
                        {
                            "project_name": project_name,
                            "package_name": package_name,
                            "path": f"{evidence_base}!/{name}",
                        }
                    )
                    packages.append(
                        {
                            "project_name": project_name,
                            "package_name": package_name,
                            "version": "",
                            "source": "nupkg/xaml",
                            "project_compatibility": compatibility,
                            "evidence": [f"{evidence_base}!/{name}"],
                        }
                    )

    project = {
        "name": project_name,
        "description": project_json.get("description", ""),
        "version": nuspec.get("version") or project_json.get("projectVersion", ""),
        "path": str(_relative(nupkg_path, root)),
        "source": "nupkg",
        "compatibility": compatibility,
        "target_framework": lib_prefix.strip("/").split("/")[-1] if lib_prefix else "",
        "xaml_files": [workflow["path"] for workflow in workflows],
    }
    return {
        "project": project,
        "packages": packages,
        "workflows": workflows,
        "xaml_references": xaml_refs,
    }


def _nupkg_lib_prefix(names: list[str]) -> Optional[str]:
    for target in NUPKG_LIB_TARGETS:
        prefix = f"lib/{target}/"
        if any(name.startswith(prefix) and name.endswith("project.json") for name in names):
            return prefix
    for name in names:
        if re.match(r"lib/[^/]+/project\.json", name):
            return name[: name.rfind("/") + 1]
    return None


def _parse_nuspec(raw_xml: bytes) -> dict[str, Any]:
    root = ET.fromstring(raw_xml)
    data: dict[str, Any] = {"dependencies": []}
    for elem in root.iter():
        local = _local_name(elem.tag)
        if local == "id" and not data.get("id"):
            data["id"] = (elem.text or "").strip()
        elif local == "version" and not data.get("version"):
            data["version"] = (elem.text or "").strip()
        elif local == "dependency":
            dep_id = elem.attrib.get("id")
            if dep_id:
                data["dependencies"].append(
                    {"id": dep_id, "version": elem.attrib.get("version", "")}
                )
    return data


def _iter_dependencies(project_json: dict[str, Any]) -> list[tuple[str, str]]:
    dependencies = project_json.get("dependencies") or {}
    pairs: list[tuple[str, str]] = []
    if isinstance(dependencies, dict):
        for package_name, value in dependencies.items():
            if isinstance(value, str):
                pairs.append((package_name, value))
            elif isinstance(value, dict):
                pairs.append((package_name, str(value.get("version", ""))))
            else:
                pairs.append((package_name, str(value)))
    elif isinstance(dependencies, list):
        for item in dependencies:
            if isinstance(item, dict):
                package_name = item.get("id") or item.get("name")
                if package_name:
                    pairs.append((package_name, str(item.get("version", ""))))
    return pairs


def _extract_packages_from_xaml_text(text: str) -> set[str]:
    return {match.group(0) for match in UIPATH_PACKAGE_RE.finditer(text)}


def _detect_compatibility(project_json: dict[str, Any], framework_hint: str) -> str:
    values = [
        framework_hint,
        _project_value(project_json, "targetFramework"),
        _project_value(project_json, "targetFrameworkVersion"),
        _project_value(project_json, "projectType"),
        _project_value(project_json, "studioProjectType"),
        _project_value(project_json, "compatibility"),
    ]
    raw = " ".join(str(value or "") for value in values).lower()
    if any(token in raw for token in ("legacy", "net45", "net461", "net462", "net472", "net48")):
        return "windows_legacy"
    if "cross" in raw or "portable" in raw or "netstandard" in raw:
        return "cross_platform"
    if "windows" in raw or "net6" in raw or "net7" in raw or "net8" in raw:
        return "windows"
    return "unknown"


def _project_value(project_json: dict[str, Any], key: str) -> Any:
    if key in project_json:
        return project_json[key]
    runtime = project_json.get("runtimeOptions")
    if isinstance(runtime, dict) and key in runtime:
        return runtime[key]
    design = project_json.get("designOptions")
    if isinstance(design, dict) and key in design:
        return design[key]
    return ""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag
