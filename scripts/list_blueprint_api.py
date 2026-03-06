#!/usr/bin/env python3
"""Scan a UE5 C++ codebase for Blueprint-exposed symbols.

Finds and reports:
- UCLASS with Blueprintable / BlueprintType
- USTRUCT with BlueprintType
- UPROPERTY with Blueprint visibility/edit specifiers
- UFUNCTION with Blueprint-callable/event/pure specifiers
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


CLASS_BP_TAGS = (
    "Blueprintable",
    "BlueprintType",
)
STRUCT_BP_TAGS = (
    "BlueprintType",
)
PROPERTY_BP_TAGS = (
    "BlueprintReadOnly",
    "BlueprintReadWrite",
    "BlueprintGetter",
    "BlueprintSetter",
)
FUNCTION_BP_TAGS = (
    "BlueprintCallable",
    "BlueprintPure",
    "BlueprintImplementableEvent",
    "BlueprintNativeEvent",
)

DECL_RE = {
    "class": re.compile(r"\bclass\s+(\w+)"),
    "struct": re.compile(r"\bstruct\s+(\w+)"),
    "property": re.compile(r"\b([A-Za-z_][\w:<>,\s\*&]+?)\s+(\w+)\s*(?:\[[^\]]*\])?\s*;"),
    "function": re.compile(r"\b([A-Za-z_][\w:<>,\s\*&]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:;|\{)"),
}


@dataclass
class Item:
    kind: str
    name: str
    file: str
    line: int
    specifiers: list[str]
    declaration: str


def iter_code_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.suffix.lower() in {".h", ".hpp", ".hh", ".hxx", ".cpp", ".cc", ".cxx"}:
            yield p


def parse_specifiers(line: str, macro: str) -> list[str]:
    m = re.search(rf"\b{macro}\s*\((.*?)\)", line)
    if not m:
        return []
    raw = m.group(1)
    # keep full tokens, remove metadata assignments
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    return tokens


def find_next_declaration(lines: list[str], start: int, kind: str) -> tuple[str, int]:
    # Look ahead a short distance for declaration after U* macro.
    pattern = DECL_RE[kind]
    for i in range(start + 1, min(start + 16, len(lines))):
        s = lines[i].strip()
        if not s or s.startswith("//"):
            continue
        m = pattern.search(s)
        if m:
            name = m.group(1) if kind in {"class", "struct"} else m.group(2)
            return name, i + 1
    return "<unknown>", start + 1


def scan_file(path: Path, root: Path) -> list[Item]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    items: list[Item] = []

    for idx, line in enumerate(lines):
        s = line.strip()

        if "UCLASS(" in s:
            specs = parse_specifiers(s, "UCLASS")
            if any(tag in specs for tag in CLASS_BP_TAGS):
                name, decl_line = find_next_declaration(lines, idx, "class")
                items.append(
                    Item(
                        kind="class",
                        name=name,
                        file=str(path.relative_to(root)),
                        line=decl_line,
                        specifiers=specs,
                        declaration=lines[decl_line - 1].strip() if 0 <= decl_line - 1 < len(lines) else "",
                    )
                )

        if "USTRUCT(" in s:
            specs = parse_specifiers(s, "USTRUCT")
            if any(tag in specs for tag in STRUCT_BP_TAGS):
                name, decl_line = find_next_declaration(lines, idx, "struct")
                items.append(
                    Item(
                        kind="struct",
                        name=name,
                        file=str(path.relative_to(root)),
                        line=decl_line,
                        specifiers=specs,
                        declaration=lines[decl_line - 1].strip() if 0 <= decl_line - 1 < len(lines) else "",
                    )
                )

        if "UPROPERTY(" in s:
            specs = parse_specifiers(s, "UPROPERTY")
            if any(tag in specs for tag in PROPERTY_BP_TAGS):
                name, decl_line = find_next_declaration(lines, idx, "property")
                items.append(
                    Item(
                        kind="property",
                        name=name,
                        file=str(path.relative_to(root)),
                        line=decl_line,
                        specifiers=specs,
                        declaration=lines[decl_line - 1].strip() if 0 <= decl_line - 1 < len(lines) else "",
                    )
                )

        if "UFUNCTION(" in s:
            specs = parse_specifiers(s, "UFUNCTION")
            if any(tag in specs for tag in FUNCTION_BP_TAGS):
                name, decl_line = find_next_declaration(lines, idx, "function")
                items.append(
                    Item(
                        kind="function",
                        name=name,
                        file=str(path.relative_to(root)),
                        line=decl_line,
                        specifiers=specs,
                        declaration=lines[decl_line - 1].strip() if 0 <= decl_line - 1 < len(lines) else "",
                    )
                )

    return items


def to_markdown(items: list[Item]) -> str:
    grouped: dict[str, list[Item]] = {k: [] for k in ["class", "struct", "property", "function"]}
    for it in items:
        grouped[it.kind].append(it)

    out = ["# UE5 Blueprint API Inventory", ""]
    out.append(f"Total: {len(items)}")
    out.append("")

    for kind in ["class", "struct", "property", "function"]:
        arr = grouped[kind]
        out.append(f"## {kind.title()} ({len(arr)})")
        if not arr:
            out.append("_None found._")
            out.append("")
            continue
        out.append("| Name | File | Line | Specifiers | Declaration |")
        out.append("|---|---|---:|---|---|")
        for it in sorted(arr, key=lambda x: (x.file, x.line, x.name)):
            specs = ", ".join(it.specifiers)
            decl = it.declaration.replace("|", "\\|")
            out.append(f"| {it.name} | `{it.file}` | {it.line} | `{specs}` | `{decl}` |")
        out.append("")

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="List UE5 Blueprint-exposed C++ symbols")
    parser.add_argument("root", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--json", dest="json_out", help="Write JSON report path")
    parser.add_argument("--md", dest="md_out", help="Write Markdown report path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    items: list[Item] = []
    for file in iter_code_files(root):
        items.extend(scan_file(file, root))

    items.sort(key=lambda x: (x.kind, x.file, x.line, x.name))

    if args.json_out:
        Path(args.json_out).write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2), encoding="utf-8")

    if args.md_out:
        Path(args.md_out).write_text(to_markdown(items), encoding="utf-8")

    if not args.json_out and not args.md_out:
        print(to_markdown(items))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
