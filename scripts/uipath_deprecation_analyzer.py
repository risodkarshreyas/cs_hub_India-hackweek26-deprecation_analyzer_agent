import argparse
import json
from datetime import date
from pathlib import Path

from activities_lifecycle import (
    DEFAULT_ACTIVITIES_LIFECYCLE_URL,
    fetch_activities_lifecycle,
)
from matcher import match_activities_lifecycle, match_deprecations
from normalizer import (
    normalize_client_finding,
    normalize_product_finding,
    normalize_server_finding,
)
from out_of_support_matcher import (
    collect_server_product_records,
    match_out_of_support_products,
)
from out_of_support_versions import (
    DEFAULT_OUT_OF_SUPPORT_URL,
    fetch_out_of_support_versions,
    platform_out_of_support_trains,
)
from project_inventory import scan_inputs
from reports import build_common_report_payload, build_report_payload, write_reports
from server_inventory import looks_like_server_input, scan_server_inputs
from server_matcher import match_server_deprecations
from server_rules import fetch_server_rules
from timeline import DEFAULT_TIMELINE_URL, fetch_timeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze UiPath client and server artifacts for deprecation risk."
    )
    parser.add_argument("--input", required=True, help="Project, repository, or nupkg folder to scan.")
    parser.add_argument("--output", required=True, help="Directory for generated reports.")
    parser.add_argument(
        "--mode",
        choices=("auto", "client", "server", "mixed"),
        default="auto",
        help="Analyzer route. Auto detects client/server evidence.",
    )
    parser.add_argument(
        "--refresh-timeline",
        action="store_true",
        help="Fetch the live UiPath timeline. Live refresh is the default; this flag is kept for compatibility.",
    )
    parser.add_argument(
        "--use-cache-only",
        action="store_true",
        help="Use the normalized timeline cache without fetching the live UiPath timeline.",
    )
    parser.add_argument("--timeline-cache", default="", help="Alias for --client-timeline-cache.")
    parser.add_argument("--client-timeline-cache", default="", help="Path to normalized client timeline cache JSON.")
    parser.add_argument("--server-rule-cache", default="", help="Path to normalized server rule cache JSON.")
    parser.add_argument(
        "--activities-lifecycle-cache",
        default="",
        help="Path to normalized activities-lifecycle cache JSON.",
    )
    parser.add_argument(
        "--out-of-support-cache",
        default="",
        help="Path to normalized out-of-support product versions cache JSON.",
    )
    parser.add_argument(
        "--activities-lifecycle-url",
        default=DEFAULT_ACTIVITIES_LIFECYCLE_URL,
        help="Override the UiPath activities-lifecycle documentation URL.",
    )
    parser.add_argument(
        "--out-of-support-url",
        default=DEFAULT_OUT_OF_SUPPORT_URL,
        help="Override the UiPath out-of-support versions documentation URL.",
    )
    parser.add_argument("--offline", action="store_true", help="Use cache files only; do not fetch live UiPath docs.")
    parser.add_argument(
        "--format",
        default="markdown,json,csv,xlsx",
        help="Comma-separated output formats: markdown,json,csv,xlsx,html,all.",
    )
    parser.add_argument("--include-xaml", action="store_true", default=True)
    parser.add_argument("--include-nupkg", action="store_true", default=True)
    parser.add_argument("--strict", action="store_true", help="Skip Windows-Legacy-only entries for non-legacy projects.")
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument("--timeline-url", default=DEFAULT_TIMELINE_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = Path(args.input)
    route = _resolve_route(args.mode, input_path)
    use_cache_only = args.use_cache_only or args.offline
    normalized_findings: list[dict] = []
    coverage_gaps: list[dict] = []
    inventory_summary: dict = {"route": route}
    raw_client_payload = {}
    product_records: list[dict] = []

    # Both the client lifecycle floor and the product-version check read the out-of-support
    # versions page, so fetch and normalize it once for every route.
    out_of_support_cache = (
        Path(args.out_of_support_cache)
        if args.out_of_support_cache
        else output_dir / "normalized_out_of_support_versions.json"
    )
    out_of_support_entries: list[dict] = []
    try:
        out_of_support_entries = fetch_out_of_support_versions(
            source_url=args.out_of_support_url,
            cache_path=out_of_support_cache,
            refresh=args.refresh_timeline,
            use_cache_only=use_cache_only,
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully when the page is unavailable
        coverage_gaps.append(
            {
                "type": "missing_source",
                "product": "UiPath products",
                "feature": "out-of-support versions",
                "message": f"Could not load the out-of-support versions page: {exc}",
            }
        )

    if route in {"client", "mixed"}:
        timeline_cache = Path(args.client_timeline_cache or args.timeline_cache) if (args.client_timeline_cache or args.timeline_cache) else output_dir / "normalized_deprecation_timeline.json"
        client_inventory = scan_inputs(
            input_path,
            include_xaml=args.include_xaml,
            include_nupkg=args.include_nupkg,
        )
        timeline_entries = fetch_timeline(
            source_url=args.timeline_url,
            cache_path=timeline_cache,
            refresh=args.refresh_timeline,
            use_cache_only=use_cache_only,
        )
        client_findings = match_deprecations(
            client_inventory,
            timeline_entries,
            analysis_date=args.analysis_date,
            strict=args.strict,
        )
        raw_client_payload = build_report_payload(
            inventory=client_inventory,
            timeline_entries=timeline_entries,
            findings=client_findings,
            analysis_date=args.analysis_date,
        )
        start = len(normalized_findings) + 1
        normalized_findings.extend(
            normalize_client_finding(finding, start + index, args.analysis_date)
            for index, finding in enumerate(client_findings)
        )

        # Out-of-support activity-package (dependency) versions, using the support floor
        # derived from the out-of-support release trains.
        lifecycle_cache = (
            Path(args.activities_lifecycle_cache)
            if args.activities_lifecycle_cache
            else output_dir / "normalized_activities_lifecycle.json"
        )
        try:
            lifecycle_entries = fetch_activities_lifecycle(
                source_url=args.activities_lifecycle_url,
                cache_path=lifecycle_cache,
                refresh=args.refresh_timeline,
                use_cache_only=use_cache_only,
            )
        except Exception as exc:  # noqa: BLE001 - degrade gracefully when the page is unavailable
            lifecycle_entries = []
            coverage_gaps.append(
                {
                    "type": "missing_source",
                    "product": "Studio/Robot activity packages",
                    "feature": "activities lifecycle",
                    "message": f"Could not load the activities lifecycle page: {exc}",
                }
            )
        oos_trains = platform_out_of_support_trains(out_of_support_entries, args.analysis_date)
        lifecycle_findings = match_activities_lifecycle(
            client_inventory,
            lifecycle_entries,
            oos_trains,
            analysis_date=args.analysis_date,
        )
        start = len(normalized_findings) + 1
        normalized_findings.extend(
            normalize_client_finding(finding, start + index, args.analysis_date)
            for index, finding in enumerate(lifecycle_findings)
        )

        # Client Studio product versions feed the shared out-of-support product check.
        for product in client_inventory.get("product_inventory", []):
            product_records.append({**product, "domain": "client"})
        inventory_summary["client"] = client_inventory.get("summary", {})

    if route in {"server", "mixed"}:
        server_cache = Path(args.server_rule_cache) if args.server_rule_cache else output_dir / "normalized_server_rules.json"
        server_inventory = scan_server_inputs(input_path)
        server_rules = fetch_server_rules(
            source_url=args.timeline_url,
            cache_path=server_cache,
            refresh=args.refresh_timeline,
            use_cache_only=use_cache_only,
        )
        server_findings, coverage_gaps = match_server_deprecations(
            server_inventory,
            server_rules,
            analysis_date=args.analysis_date,
        )
        start = len(normalized_findings) + 1
        normalized_findings.extend(
            normalize_server_finding(finding, start + index, args.analysis_date)
            for index, finding in enumerate(server_findings)
        )
        product_records.extend(collect_server_product_records(server_inventory))
        inventory_summary["server"] = server_inventory.get("summary", {})

    # Shared out-of-support product-version check across client Studio and server products.
    if out_of_support_entries and product_records:
        product_findings = match_out_of_support_products(
            product_records,
            out_of_support_entries,
            analysis_date=args.analysis_date,
        )
        start = len(normalized_findings) + 1
        normalized_findings.extend(
            normalize_product_finding(finding, start + index, args.analysis_date)
            for index, finding in enumerate(product_findings)
        )

    payload = build_common_report_payload(
        findings=normalized_findings,
        analysis_date=args.analysis_date,
        coverage_gaps=coverage_gaps,
        inventory={"summary": inventory_summary},
        raw_client_payload=raw_client_payload,
    )
    formats = [item.strip() for item in args.format.split(",") if item.strip()]
    paths = write_reports(payload, output_dir, formats)
    print(json.dumps({"reports": paths, "findings": len(normalized_findings), "route": route}, indent=2))
    return 0


def _resolve_route(mode: str, input_path: Path) -> str:
    if mode != "auto":
        return mode
    client_markers = {".xaml", ".nupkg"}
    files = [input_path] if input_path.is_file() else list(input_path.rglob("*")) if input_path.exists() else []
    has_client = any(path.name == "project.json" or path.suffix.lower() in client_markers for path in files)
    has_server = looks_like_server_input(input_path)
    if has_client and has_server:
        return "mixed"
    if has_server:
        return "server"
    return "client"


if __name__ == "__main__":
    raise SystemExit(main())
