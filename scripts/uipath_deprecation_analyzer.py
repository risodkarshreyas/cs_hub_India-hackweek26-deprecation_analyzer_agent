import argparse
import json
from datetime import date
from pathlib import Path

from matcher import match_deprecations
from project_inventory import scan_inputs
from reports import build_report_payload, write_reports
from timeline import DEFAULT_TIMELINE_URL, fetch_timeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze UiPath projects and nupkg packages for deprecated activity packages."
    )
    parser.add_argument("--input", required=True, help="Project, repository, or nupkg folder to scan.")
    parser.add_argument("--output", required=True, help="Directory for generated reports.")
    parser.add_argument("--refresh-timeline", action="store_true", help="Fetch the live UiPath timeline.")
    parser.add_argument("--timeline-cache", default="", help="Path to normalized timeline cache JSON.")
    parser.add_argument(
        "--format",
        default="markdown,json,csv,xlsx",
        help="Comma-separated output formats: markdown,json,csv,xlsx,all.",
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
    timeline_cache = (
        Path(args.timeline_cache)
        if args.timeline_cache
        else output_dir / "normalized_deprecation_timeline.json"
    )

    inventory = scan_inputs(
        Path(args.input),
        include_xaml=args.include_xaml,
        include_nupkg=args.include_nupkg,
    )
    timeline_entries = fetch_timeline(
        source_url=args.timeline_url,
        cache_path=timeline_cache,
        refresh=args.refresh_timeline,
    )
    findings = match_deprecations(
        inventory,
        timeline_entries,
        analysis_date=args.analysis_date,
        strict=args.strict,
    )
    payload = build_report_payload(
        inventory=inventory,
        timeline_entries=timeline_entries,
        findings=findings,
        analysis_date=args.analysis_date,
    )
    formats = [item.strip() for item in args.format.split(",") if item.strip()]
    paths = write_reports(payload, output_dir, formats)
    print(json.dumps({"reports": paths, "findings": len(findings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
