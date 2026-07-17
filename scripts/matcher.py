import re
from datetime import date, datetime
from typing import Any, Optional


WINDOWS_LEGACY_CLASSIFICATION = ".NET Framework 4.6.1 / Windows-Legacy Compatibility Impact"
OUT_OF_SUPPORT_CLASSIFICATION = "Out Of Support"


def match_deprecations(
    inventory: dict[str, Any],
    timeline_entries: list[dict[str, Any]],
    analysis_date: Optional[str] = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Match scanned package inventory against normalized UiPath timeline entries.

    Inputs are intentionally plain dictionaries because this module is the join
    point between scanner output, timeline parsing, and report generation. The
    matcher enriches package evidence with classification, recommendations,
    remediation guidance, and impact estimates.
    """
    as_of = _parse_date(analysis_date) or date.today()
    projects = {
        project.get("name"): project for project in inventory.get("projects", [])
    }
    findings: list[dict[str, Any]] = []

    # Evaluate every scanned package against every normalized timeline entry.
    # The first guard is exact package name matching; this avoids false positives
    # from broad timeline text or non-package deprecations.
    for package in inventory.get("package_inventory", []):
        package_name = package.get("package_name", "")
        for entry in timeline_entries:
            if package_name.lower() != entry.get("package_name", "").lower():
                continue
            project = projects.get(package.get("project_name"), {})

            # Compatibility and version checks are separate so reviewers can see
            # why a potential timeline match was intentionally skipped.
            if not _entry_applies_to_project(entry, project, package, strict):
                continue
            if not _version_applies(package.get("version", ""), entry.get("affected_version", "")):
                continue

            classification = _classify(entry, as_of, project)
            recommendation = _recommendation(entry, classification)
            risk, urgency = _risk_and_urgency(classification)
            findings.append(
                {
                    "project_name": package.get("project_name", ""),
                    "package_name": package_name,
                    "current_version": package.get("version", ""),
                    "classification": classification,
                    "risk_level": risk,
                    "urgency": urgency,
                    "recommendation": recommendation,
                    "replacement_package": entry.get("replacement_package", ""),
                    "affected_version": entry.get("affected_version", ""),
                    "deprecation_date": entry.get("deprecation_date", ""),
                    "removal_date": entry.get("removal_date", ""),
                    "compatibility_scope": entry.get("compatibility_scope", ""),
                    "project_compatibility": project.get("compatibility") or package.get("project_compatibility", ""),
                    "evidence": package.get("evidence", []),
                    "source_url": entry.get("source_url", ""),
                    "source_section_title": entry.get("source_section_title", ""),
                    "source_text": entry.get("source_text", ""),
                    "confidence": _combined_confidence(entry, package),
                    "owner_action": _owner_action(classification),
                    "validation_steps": _validation_steps(classification),
                    "impact": _impact_estimate(inventory, package, classification),
                }
            )

    # Put the riskiest items first so reports naturally lead with work that
    # needs attention before lower-risk scheduled removals.
    findings.sort(key=lambda item: (_risk_rank(item["risk_level"]), item["package_name"]))
    return findings


def match_activities_lifecycle(
    inventory: dict[str, Any],
    lifecycle_entries: list[dict[str, Any]],
    out_of_support_trains: dict[str, str],
    analysis_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Flag installed activity-package versions that are below the supported version floor.

    The activities-lifecycle page maps each package to the version shipped in every release
    train. A train is out of support when it appears in ``out_of_support_trains`` (derived
    from the out-of-support versions page relative to the analysis date). The support floor
    for a package is the version shipped in the oldest still-supported train; an installed
    version below that floor is out of support.
    """
    as_of = _parse_date(analysis_date) or date.today()
    projects = {project.get("name"): project for project in inventory.get("projects", [])}
    entries_by_package = {
        entry.get("package_name", "").lower(): entry for entry in lifecycle_entries
    }
    findings: list[dict[str, Any]] = []

    for package in inventory.get("package_inventory", []):
        current_version = package.get("version", "")
        if not current_version:
            continue  # XAML-only references carry no version to compare.
        entry = entries_by_package.get(package.get("package_name", "").lower())
        if not entry:
            continue
        floor = _supported_version_floor(entry, out_of_support_trains)
        if not floor:
            continue  # No supported train resolved; avoid a false positive.
        if _version_tuple(current_version) >= _version_tuple(floor["version"]):
            continue

        owning = _owning_release(entry, current_version)
        out_of_support_since = ""
        release_label = ""
        if owning:
            release_label = owning.get("release_label", "")
            out_of_support_since = out_of_support_trains.get(owning.get("release_train", ""), "")
        project = projects.get(package.get("project_name"), {})
        recommendation = (
            f"Upgrade {package.get('package_name', '')} to at least {floor['version']} "
            f"({floor['release_label']}) to return to a supported release."
        )
        findings.append(
            {
                "project_name": package.get("project_name", ""),
                "package_name": package.get("package_name", ""),
                "current_version": current_version,
                "classification": OUT_OF_SUPPORT_CLASSIFICATION,
                "risk_level": "High",
                "urgency": "Upgrade to a supported version",
                "recommendation": recommendation,
                "replacement_package": "",
                "affected_version": f"< {floor['version']}",
                "min_supported_version": floor["version"],
                "deprecation_date": "",
                "removal_date": out_of_support_since,
                "compatibility_scope": "all_projects",
                "project_compatibility": project.get("compatibility")
                or package.get("project_compatibility", ""),
                "evidence": package.get("evidence", []),
                "source_url": entry.get("source_url", ""),
                "source_section_title": entry.get("source_section_title", ""),
                "source_text": (
                    f"{package.get('package_name', '')} {current_version} maps to "
                    f"{release_label or 'an out-of-support release train'}; minimum supported "
                    f"version is {floor['version']} ({floor['release_label']})."
                ),
                "confidence": _combined_confidence(entry, package),
                "owner_action": _owner_action(OUT_OF_SUPPORT_CLASSIFICATION),
                "validation_steps": _validation_steps(OUT_OF_SUPPORT_CLASSIFICATION),
                "impact": _impact_estimate(inventory, package, OUT_OF_SUPPORT_CLASSIFICATION),
            }
        )

    findings.sort(key=lambda item: (_risk_rank(item["risk_level"]), item["package_name"]))
    return findings


def _supported_version_floor(
    entry: dict[str, Any],
    out_of_support_trains: dict[str, str],
) -> Optional[dict[str, str]]:
    """Return the lowest version shipped in a still-supported release train."""
    supported = [
        release
        for release in entry.get("versions_by_release", [])
        if release.get("version")
        and release.get("release_train")
        and release["release_train"] not in out_of_support_trains
    ]
    if not supported:
        return None
    return min(supported, key=lambda release: _version_tuple(release["version"]))


def _owning_release(entry: dict[str, Any], current_version: str) -> Optional[dict[str, str]]:
    """Find the newest release train whose shipped version is at or below the installed one."""
    current = _version_tuple(current_version)
    candidates = [
        release
        for release in entry.get("versions_by_release", [])
        if release.get("version") and _version_tuple(release["version"]) <= current
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda release: _version_tuple(release["version"]))


def _classify(entry: dict[str, Any], analysis_date: date, project: dict[str, Any]) -> str:
    """Assign the timeline category using the requested analysis date."""
    removal_date = _parse_date(entry.get("removal_date"))
    if removal_date:
        delta = (removal_date - analysis_date).days
        if delta < 0:
            return "Already Removed"
        # Six months and eighteen months are represented as day counts to keep
        # the logic deterministic without adding date arithmetic dependencies.
        if delta <= 183:
            return "Removal Imminent"
        if delta <= 548:
            return "Removal Scheduled"
    if (
        entry.get("compatibility_scope") == "windows_legacy_only"
        and project.get("compatibility") == "windows_legacy"
    ):
        return WINDOWS_LEGACY_CLASSIFICATION
    return "Removal Scheduled"


def _entry_applies_to_project(
    entry: dict[str, Any],
    project: dict[str, Any],
    package: dict[str, Any],
    strict: bool,
) -> bool:
    """Decide whether a timeline entry can apply to the current project."""
    scope = entry.get("compatibility_scope")
    if scope != "windows_legacy_only":
        return True
    compatibility = project.get("compatibility") or package.get("project_compatibility")
    if compatibility == "windows_legacy":
        return True

    # Known Windows or Cross-platform projects should not be flagged by entries
    # that only describe Windows-Legacy/.NET Framework 4.6.1 compatibility.
    if compatibility in {"windows", "cross_platform"}:
        return False

    # Unknown compatibility is included by default so auditors can review it.
    # In strict mode, unknown projects are skipped to minimize false positives.
    return not strict


def _version_applies(current_version: str, affected_version: str) -> bool:
    """Return whether the installed version is covered by the timeline entry."""
    if not affected_version or not current_version:
        return True
    current = _version_tuple(current_version)
    affected = affected_version.strip()

    # The normalized timeline may contain broad hints rather than formal NuGet
    # ranges. Support the patterns we emit today: prefix ranges and simple
    # comparison operators.
    if affected.endswith(".x"):
        return current_version.startswith(affected[:-2] + ".")
    if affected.startswith("<="):
        return current <= _version_tuple(affected[2:])
    if affected.startswith("<"):
        return current < _version_tuple(affected[1:])
    if affected.startswith(">="):
        return current >= _version_tuple(affected[2:])
    if affected.startswith(">"):
        return current > _version_tuple(affected[1:])
    return current == _version_tuple(affected)


def _recommendation(entry: dict[str, Any], classification: str) -> str:
    """Create remediation text without inventing undocumented replacements."""
    replacement = entry.get("replacement_package")
    if replacement:
        return f"Replace with {replacement}."
    if classification == OUT_OF_SUPPORT_CLASSIFICATION:
        return "Upgrade the package to a version shipped in a currently supported release train."
    if "Windows-Legacy" in classification:
        return "Migrate from Windows-Legacy or pin to the last supported package version documented by UiPath."
    return "No direct replacement stated - review manually."


def _risk_and_urgency(classification: str) -> tuple[str, str]:
    """Map classifications to the report-facing risk and urgency labels."""
    if classification == "Already Removed":
        return "Critical", "Immediate"
    if classification == OUT_OF_SUPPORT_CLASSIFICATION:
        return "High", "Upgrade to a supported version"
    if classification == "Removal Imminent":
        return "High", "Next 0-6 months"
    if classification == "Removal Scheduled":
        return "Medium", "Plan within 6-18 months"
    if "Windows-Legacy" in classification:
        return "High", "Prioritize Windows/Cross-platform migration planning"
    return "Medium", "Review"


def _owner_action(classification: str) -> str:
    """Suggest the next owner-level action for remediation planning."""
    if classification == "Already Removed":
        return "Assign migration owner and remediate before next package upgrade or deployment."
    if classification == OUT_OF_SUPPORT_CLASSIFICATION:
        return "Plan a package upgrade to a supported release train in the next maintenance window."
    if classification == "Removal Imminent":
        return "Schedule migration in the next release cycle."
    if "Windows-Legacy" in classification:
        return "Confirm project compatibility mode and plan migration from Windows-Legacy."
    return "Add to remediation backlog and track against removal date."


def _validation_steps(classification: str) -> list[str]:
    """Return practical validation checks after a package remediation."""
    steps = [
        "Update package references in project.json or package manager.",
        "Open the project in UiPath Studio and resolve missing activities.",
        "Run workflow validation and smoke-test affected entry points.",
    ]
    if classification == OUT_OF_SUPPORT_CLASSIFICATION:
        steps.insert(0, "Confirm the target supported package version against the UiPath activities lifecycle page.")
    if "Windows-Legacy" in classification:
        steps.insert(0, "Validate whether the project still targets Windows-Legacy/.NET Framework 4.6.1.")
    return steps


def _impact_estimate(
    inventory: dict[str, Any],
    package: dict[str, Any],
    classification: str,
) -> dict[str, Any]:
    """Estimate impact using evidence already available from the scanner.

    These estimates are intentionally conservative. If workflow evidence is
    missing, the output lowers confidence instead of pretending precision.
    """
    project_name = package.get("project_name")
    workflow_count = sum(
        1
        for workflow in inventory.get("workflow_inventory", [])
        if workflow.get("project_name") == project_name
    )
    effort = "medium"
    if classification == "Already Removed":
        effort = "high"
    elif workflow_count <= 1:
        effort = "low"
    return {
        "affected_project_count": 1 if project_name else 0,
        "affected_workflow_count": workflow_count,
        "affected_package_count": 1,
        "remediation_effort": effort,
        "likely_migration_complexity": effort,
        "estimated_time_saved": "2-6 hours of manual package and XAML review per affected project",
        "value_added": "Early detection of removal risk with evidence paths and migration guidance",
        "confidence": "medium" if workflow_count else "low",
    }


def _combined_confidence(entry: dict[str, Any], package: dict[str, Any]) -> str:
    """Combine timeline extraction confidence with local evidence strength."""
    if entry.get("confidence") == "high" and package.get("evidence"):
        return "high"
    if package.get("evidence"):
        return "medium"
    return "low"


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse normalized YYYY-MM-DD dates; invalid or absent dates are unknown."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _version_tuple(value: str) -> tuple[int, ...]:
    """Convert a NuGet-like version string to a tuple for simple comparisons."""
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts) if parts else (0,)


def _risk_rank(value: str) -> int:
    """Sort report rows from highest to lowest risk."""
    return {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(value, 9)
