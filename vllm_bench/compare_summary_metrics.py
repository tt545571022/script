#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


KEY_FIELDS = (
    "request_rate",
    "max_concurrency",
    "num_prompts",
    "input_start",
    "output_start",
)

THROUGHPUT_CHOICES = {
    "request": "request_throughput",
    "output": "output_token_throughput",
    "total": "total_token_throughput",
}

THROUGHPUT_SHORT_LABELS = {
    "request_throughput": "req/s",
    "output_token_throughput": "out tok/s",
    "total_token_throughput": "tot tok/s",
}

COLUMN_SPECS = (
    ("case", ("conc", "prom", "in", "out")),
    ("baseline_throughput", ("base", "{throughput_short}")),
    ("target_throughput", ("tgt", "{throughput_short}")),
    ("throughput_delta_pct", ("{throughput_short}", "d%")),
    ("baseline_output_throughput", ("base", "out tok/s")),
    ("target_output_throughput", ("tgt", "out tok/s")),
    (
        "output_throughput_delta_pct",
        ("out tok/s", "d%"),
    ),
    ("baseline_mean_ttft_ms", ("base", "ttft ms")),
    ("target_mean_ttft_ms", ("tgt", "ttft ms")),
    ("ttft_improvement_pct", ("ttft", "d%")),
    ("baseline_mean_tpot_ms", ("base", "tpot ms")),
    ("target_mean_tpot_ms", ("tgt", "tpot ms")),
    ("tpot_improvement_pct", ("tpot", "d%")),
)


def improvement_pct_higher_better(baseline: float, target: float) -> float:
    return (target / baseline - 1.0) * 100.0


def improvement_pct_lower_better(baseline: float, target: float) -> float:
    return (baseline - target) / baseline * 100.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare vLLM benchmark summary CSVs for two modes, focusing on "
            "throughput, mean TTFT, and mean TPOT."
        )
    )
    parser.add_argument(
        "result_dir",
        type=Path,
        help="Directory containing benchmark result subdirectories.",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help=(
            "Baseline subdirectory name. If omitted, use the first subdirectory "
            "by name under result_dir."
        ),
    )
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "Target subdirectory name. If omitted, use the second subdirectory "
            "by name under result_dir."
        ),
    )
    parser.add_argument(
        "--throughput",
        choices=tuple(THROUGHPUT_CHOICES),
        default="total",
        help="Which throughput column to compare. Default: total.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Optional path to write the comparison rows as CSV.",
    )
    parser.add_argument(
        "--skip-first",
        type=int,
        default=0,
        help="Skip the first N matched benchmark rows after sorting. Default: 0.",
    )
    return parser.parse_args()


def find_summary_csv(mode_dir: Path) -> Path:
    matches = sorted(mode_dir.glob("*-summary.csv"))
    if not matches:
        raise FileNotFoundError(f"No summary CSV found under {mode_dir}")
    if len(matches) > 1:
        raise RuntimeError(
            f"Expected exactly one summary CSV under {mode_dir}, found {len(matches)}"
        )
    return matches[0]


def resolve_mode_dirs(
    result_dir: Path,
    baseline_name: str | None,
    target_name: str | None,
) -> tuple[Path, Path, str, str]:
    subdirs = sorted([path for path in result_dir.iterdir() if path.is_dir()])
    if len(subdirs) < 2:
        raise RuntimeError(
            f"Need at least 2 subdirectories under {result_dir}, found {len(subdirs)}"
        )

    if baseline_name is None and target_name is None:
        baseline_dir = subdirs[0]
        target_dir = subdirs[1]
    else:
        baseline_dir = result_dir / baseline_name if baseline_name else None
        target_dir = result_dir / target_name if target_name else None

        if baseline_dir is None:
            baseline_dir = next((path for path in subdirs if path != target_dir), None)
        if target_dir is None:
            target_dir = next((path for path in subdirs if path != baseline_dir), None)

    if baseline_dir is None or target_dir is None:
        raise RuntimeError("Could not resolve baseline/target directories.")
    if not baseline_dir.is_dir():
        raise FileNotFoundError(f"Baseline directory does not exist: {baseline_dir}")
    if not target_dir.is_dir():
        raise FileNotFoundError(f"Target directory does not exist: {target_dir}")
    if baseline_dir == target_dir:
        raise RuntimeError(f"Baseline and target must be different: {baseline_dir}")

    return baseline_dir, target_dir, baseline_dir.name, target_dir.name


def load_rows(csv_path: Path) -> tuple[list[tuple[str, ...]], dict[tuple[str, ...], dict[str, str]]]:
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        order: list[tuple[str, ...]] = []
        rows: dict[tuple[str, ...], dict[str, str]] = {}
        for row in reader:
            key = tuple(row[field] for field in KEY_FIELDS)
            order.append(key)
            rows[key] = row
    return order, rows


def as_float(row: dict[str, str], field: str) -> float:
    value = row.get(field)
    if value is None or value == "":
        raise ValueError(f"Missing field {field}")
    return float(value)


def build_case_value(row: dict[str, str]) -> str:
    return (
        f"{row['max_concurrency']}-"
        f"{row['num_prompts']}-"
        f"{row['input_start']}-"
        f"{row['output_start']}"
    )


def two_line_label(*parts: str) -> str:
    words: list[str] = []
    for part in parts:
        normalized = part.replace("_", " ").replace("-", " ").strip()
        if normalized:
            words.extend(normalized.split())
    if len(words) <= 2:
        return " ".join(words) + "\n"

    split_idx = (len(words) + 1) // 2
    line1 = " ".join(words[:split_idx])
    line2 = " ".join(words[split_idx:])
    return f"{line1}\n{line2}"


def single_line_label(*parts: str) -> str:
    words: list[str] = []
    for part in parts:
        normalized = part.replace("_", " ").replace("-", " ").strip()
        if normalized:
            words.extend(normalized.split())
    return " ".join(words)


def build_header_map(throughput_field: str, style: str) -> dict[str, str]:
    renderer = two_line_label if style == "multi" else single_line_label
    throughput_short = THROUGHPUT_SHORT_LABELS.get(throughput_field, throughput_field)
    header_map: dict[str, str] = {}
    for key, raw_parts in COLUMN_SPECS:
        parts = tuple(
            part.format(
                throughput_field=throughput_field,
                throughput_short=throughput_short,
            )
            for part in raw_parts
        )
        header_map[key] = renderer(*parts)
    return header_map


def remap_rows(
    rows: list[dict[str, str]],
    ordered_keys: list[str],
    header_map: dict[str, str],
) -> list[dict[str, str]]:
    remapped: list[dict[str, str]] = []
    for row in rows:
        remapped.append({header_map[key]: row[key] for key in ordered_keys})
    return remapped


def format_table(rows: list[dict[str, str]]) -> str:
    headers = list(rows[0].keys())
    header_lines = {header: header.split("\n") for header in headers}
    widths = {
        header: max(len(part) for part in header_lines[header])
        for header in headers
    }
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(row[header]))

    def render_row(row: dict[str, str]) -> str:
        return " | ".join(row[h].ljust(widths[h]) for h in headers)

    max_header_lines = max(len(header_lines[header]) for header in headers)
    rendered_headers: list[str] = []
    for line_idx in range(max_header_lines):
        rendered_headers.append(
            " | ".join(
                (
                    header_lines[header][line_idx]
                    if line_idx < len(header_lines[header])
                    else ""
                ).ljust(widths[header])
                for header in headers
            )
        )

    separator = "-+-".join("-" * widths[h] for h in headers)
    output = rendered_headers + [separator]
    output.extend(render_row(row) for row in rows)
    return "\n".join(output)


def main() -> int:
    args = parse_args()
    result_dir = args.result_dir.resolve()
    baseline_dir, target_dir, baseline_name, target_name = resolve_mode_dirs(
        result_dir,
        args.baseline,
        args.target,
    )

    baseline_csv = find_summary_csv(baseline_dir)
    target_csv = find_summary_csv(target_dir)
    baseline_order, baseline_rows = load_rows(baseline_csv)
    target_order, target_rows = load_rows(target_csv)

    missing = sorted(set(baseline_rows) ^ set(target_rows))
    if missing:
        print("Mismatched benchmark cases between the two CSVs:", file=sys.stderr)
        for key in missing:
            print("  " + ", ".join(key), file=sys.stderr)
        return 1

    throughput_field = THROUGHPUT_CHOICES[args.throughput]
    ordered_keys = [key for key, _ in COLUMN_SPECS]
    comparison_rows: list[dict[str, str]] = []

    sorted_keys = baseline_order
    if args.skip_first > 0:
        sorted_keys = sorted_keys[args.skip_first:]

    target_order_set = set(target_order)
    sorted_keys = [key for key in sorted_keys if key in target_order_set]

    for key in sorted_keys:
        base_row = baseline_rows[key]
        target_row = target_rows[key]

        base_throughput = as_float(base_row, throughput_field)
        target_throughput = as_float(target_row, throughput_field)
        base_output_throughput = as_float(base_row, "output_token_throughput")
        target_output_throughput = as_float(target_row, "output_token_throughput")
        base_ttft = as_float(base_row, "mean_ttft")
        target_ttft = as_float(target_row, "mean_ttft")
        base_tpot = as_float(base_row, "mean_tpot")
        target_tpot = as_float(target_row, "mean_tpot")

        throughput_delta_pct = improvement_pct_higher_better(
            base_throughput,
            target_throughput,
        )
        output_throughput_delta_pct = improvement_pct_higher_better(
            base_output_throughput,
            target_output_throughput,
        )
        ttft_improvement_pct = improvement_pct_lower_better(base_ttft, target_ttft)
        tpot_improvement_pct = improvement_pct_lower_better(base_tpot, target_tpot)

        comparison_rows.append(
            {
                "case": build_case_value(base_row),
                "baseline_throughput": f"{base_throughput:.2f}",
                "target_throughput": f"{target_throughput:.2f}",
                "baseline_output_throughput": f"{base_output_throughput:.2f}",
                "target_output_throughput": f"{target_output_throughput:.2f}",
                "output_throughput_delta_pct": f"{output_throughput_delta_pct:+.2f}%",
                "throughput_delta_pct": f"{throughput_delta_pct:+.2f}%",
                "baseline_mean_ttft_ms": f"{base_ttft:.2f}",
                "target_mean_ttft_ms": f"{target_ttft:.2f}",
                "ttft_improvement_pct": f"{ttft_improvement_pct:+.2f}%",
                "baseline_mean_tpot_ms": f"{base_tpot:.2f}",
                "target_mean_tpot_ms": f"{target_tpot:.2f}",
                "tpot_improvement_pct": f"{tpot_improvement_pct:+.2f}%",
            }
        )

    if not comparison_rows:
        print("No benchmark rows found.", file=sys.stderr)
        return 1

    print(f"baseline_csv={baseline_csv}")
    print(f"target_csv={target_csv}")
    print(f"baseline_mode={baseline_name}")
    print(f"target_mode={target_name}")
    print(f"throughput_field={throughput_field}")
    print(f"skip_first={args.skip_first}")
    print()

    table_headers = build_header_map(throughput_field, "multi")
    table_rows = remap_rows(comparison_rows, ordered_keys, table_headers)
    print(format_table(table_rows))

    if args.output_csv:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        csv_headers = build_header_map(throughput_field, "single")
        csv_rows = remap_rows(comparison_rows, ordered_keys, csv_headers)
        with args.output_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)
        print()
        print(f"comparison_csv_written: {args.output_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())