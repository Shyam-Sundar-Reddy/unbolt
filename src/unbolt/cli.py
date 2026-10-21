"""Thin CLI wrappers over unbolt's core - each command calls one core
function; if a command starts accumulating logic, that logic belongs in
core instead (CLAUDE.md). stdlib argparse: no new runtime dependency
justified for a handful of subcommands with simple flags.
"""

import argparse
import sys
from pathlib import Path

from unbolt.dsl import Dsl, build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import candidate_names, recommend_mappings
from unbolt.overrides import apply_override, load_overrides, save_overrides
from unbolt.overrides.persistence import DEFAULT_OVERRIDES_PATH
from unbolt.parser import parse_copybook
from unbolt.reporting import build_report, render_json, render_markdown
from unbolt.validation import validate_conversion


def _load_dsl(file: str) -> Dsl:
    source = Path(file).read_text()
    return build_dsl(parse_copybook(source), source_file=file)


def cmd_parse(args: argparse.Namespace) -> None:
    result = parse_copybook(Path(args.file).read_text())
    for d in result.diagnostics:
        print(f"{d.code} [{d.severity}] line {d.line}: {d.message}")
    if not result.diagnostics:
        print("no diagnostics")


def cmd_dsl(args: argparse.Namespace) -> None:
    print(_load_dsl(args.file).to_json())


def cmd_recommend(args: argparse.Namespace) -> None:
    report = recommend_mappings(_load_dsl(args.file), args.target)
    for field in report.fields:
        print(field.field_path)
        for c in field.candidates:
            print(f"  {c.status:12} {c.type_name:20} {c.rationale}")


def cmd_override(args: argparse.Namespace) -> None:
    report = recommend_mappings(_load_dsl(args.file), args.target)
    valid_choices = candidate_names(report, args.field_path)
    overrides = load_overrides(args.overrides_file)
    overrides = apply_override(
        overrides, args.field_path, args.type, args.reason,
        valid_choices=valid_choices, force=args.force,
    )
    save_overrides(overrides, args.overrides_file)
    print(f"saved: {args.field_path} -> {args.type}")


def cmd_generate(args: argparse.Namespace) -> None:
    dsl = _load_dsl(args.file)
    report = recommend_mappings(dsl, args.target)
    overrides = load_overrides(args.overrides_file)
    files = generate_code(dsl, report, args.target, overrides=overrides)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        (out_dir / rel_path).write_text(content)
        print(f"wrote {out_dir / rel_path}")


def cmd_validate(args: argparse.Namespace) -> None:
    dsl = _load_dsl(args.file)
    report = recommend_mappings(dsl, args.target)
    overrides = load_overrides(args.overrides_file)
    generated = generate_code(dsl, report, args.target, overrides=overrides)
    validation = validate_conversion(dsl, report, generated)
    for f in validation.findings:
        print(f"{f.severity:8} {f.code:20} {f.field_path}: {f.message}")
    if not validation.findings:
        print("no findings")


def cmd_mcp(args: argparse.Namespace) -> None:
    # Lazy import: mcp_server needs fastmcp (the [mcp] extra), which the
    # base `unbolt` install doesn't require - only paid for if you use it.
    from unbolt.mcp_server import main as run_mcp_server

    run_mcp_server()


def cmd_report(args: argparse.Namespace) -> None:
    dsl = _load_dsl(args.file)
    mapping = recommend_mappings(dsl, args.target)
    overrides = load_overrides(args.overrides_file)
    generated = generate_code(dsl, mapping, args.target, overrides=overrides)
    validation = validate_conversion(dsl, mapping, generated)
    report = build_report(dsl, mapping, validation, overrides=overrides)
    text = render_json(report) if args.format == "json" else render_markdown(report)
    print(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unbolt")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func: "object", *, needs_target: bool = False) -> argparse.ArgumentParser:
        p = sub.add_parser(name)
        p.add_argument("file")
        if needs_target:
            p.add_argument("--target", choices=["go", "java"], required=True)
            p.add_argument("--overrides-file", default=DEFAULT_OVERRIDES_PATH)
        p.set_defaults(func=func)
        return p

    add("parse", cmd_parse)
    add("dsl", cmd_dsl)
    add("recommend", cmd_recommend, needs_target=True)

    override = add("override", cmd_override, needs_target=True)
    override.add_argument("field_path")
    override.add_argument("type")
    override.add_argument("--reason", required=True)
    override.add_argument("--force", action="store_true")

    generate = add("generate", cmd_generate, needs_target=True)
    generate.add_argument("-o", "--output", required=True)

    add("validate", cmd_validate, needs_target=True)

    report = add("report", cmd_report, needs_target=True)
    report.add_argument("--format", choices=["md", "json"], default="md")

    mcp_parser = sub.add_parser("mcp")
    mcp_parser.set_defaults(func=cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
