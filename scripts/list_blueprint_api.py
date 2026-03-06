#!/usr/bin/env python3
"""Scan a UE5 C++ codebase for Blueprint-exposed symbols.

Finds and reports Blueprint-usable declarations in C++ headers/sources:
- UCLASS with Blueprintable / BlueprintType
- UINTERFACE with Blueprintable / BlueprintType
- USTRUCT with BlueprintType
- UENUM with BlueprintType
- UPROPERTY with Blueprint visibility/edit specifiers
- UFUNCTION with Blueprint-callable/event/pure specifiers
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator


CLASS_BP_TAGS = {"Blueprintable", "BlueprintType"}
INTERFACE_BP_TAGS = {"Blueprintable", "BlueprintType"}
STRUCT_BP_TAGS = {"BlueprintType"}
ENUM_BP_TAGS = {"BlueprintType"}
PROPERTY_BP_TAGS = {
    "BlueprintReadOnly",
    "BlueprintReadWrite",
    "BlueprintGetter",
    "BlueprintSetter",
}
FUNCTION_BP_TAGS = {
    "BlueprintCallable",
    "BlueprintPure",
    "BlueprintImplementableEvent",
    "BlueprintNativeEvent",
}


DECL_RE = {
    "class": re.compile(r"\bclass\s+(\w+)"),
    "struct": re.compile(r"\bstruct\s+(\w+)"),
    "enum": re.compile(r"\benum\s+(?:class\s+)?(\w+)"),
    # UE coding style: declaration usually appears on one line after UPROPERTY/UFUNCTION.
    "property": re.compile(r"\b([A-Za-z_][\w:<>,\s\*&]+?)\s+(\w+)\s*(?:\[[^\]]*\])?\s*;"),
    "function": re.compile(r"\b([A-Za-z_][\w:<>,\s\*&~]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:;|\{)"),
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


def tokenize_specifiers(raw: str) -> list[str]:
    """Split macro arguments by commas while respecting nested () and []."""
    out: list[str] = []
    cur: list[str] = []
    paren = 0
    bracket = 0

    for ch in raw:
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)

        if ch == "," and paren == 0 and bracket == 0:
            token = "".join(cur).strip()
            if token:
                out.append(token)
            cur = []
            continue

        cur.append(ch)

    token = "".join(cur).strip()
    if token:
        out.append(token)

    return out


def collect_macro_invocations(lines: list[str], macro: str) -> Iterator[tuple[int, int, list[str]]]:
    """Yield (start_line_1_based, end_line_1_based, specifiers) for macro blocks.

    Supports both single-line and multi-line macro arguments.
    """
    start_pat = f"{macro}("
    i = 0
    while i < len(lines):
        line = lines[i]
        pos = line.find(start_pat)
        if pos < 0:
            i += 1
            continue

        text = line[pos + len(macro):]
        depth = 0
        buf: list[str] = []
        started = False
        j = i

        while j < len(lines):
            seg = lines[j]
            if j == i:
                seg = seg[pos + len(macro):]

            for ch in seg:
                if ch == "(":
                    depth += 1
                    started = True
                    if depth == 1:
                        continue
                elif ch == ")":
                    if depth == 1:
                        depth -= 1
                        started = False
                        break
                    if depth > 0:
                        depth -= 1

                if started:
                    buf.append(ch)

            if depth == 0 and not started:
                break
            if started:
                buf.append("\n")
            j += 1

        specs = tokenize_specifiers("".join(buf))
        yield (i + 1, j + 1, specs)
        i = j + 1


def has_any_tag(specifiers: list[str], tags: set[str]) -> bool:
    for spec in specifiers:
        key = spec.split("=", 1)[0].strip()
        if key in tags:
            return True
    return False


def find_next_declaration(lines: list[str], start_1: int, kind: str) -> tuple[str, int, str]:
    pattern = DECL_RE[kind]
    start = max(0, start_1)
    for idx in range(start, min(start + 30, len(lines))):
        s = lines[idx].strip()
        if not s or s.startswith("//"):
            continue
        m = pattern.search(s)
        if m:
            name = m.group(1) if kind in {"class", "struct", "enum"} else m.group(2)
            return name, idx + 1, s
    return "<unknown>", start_1, ""


def scan_file(path: Path, root: Path) -> list[Item]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    items: list[Item] = []

    macro_rules: list[tuple[str, str, set[str], str]] = [
        ("UCLASS", "class", CLASS_BP_TAGS, "class"),
        ("UINTERFACE", "interface", INTERFACE_BP_TAGS, "class"),
        ("USTRUCT", "struct", STRUCT_BP_TAGS, "struct"),
        ("UENUM", "enum", ENUM_BP_TAGS, "enum"),
        ("UPROPERTY", "property", PROPERTY_BP_TAGS, "property"),
        ("UFUNCTION", "function", FUNCTION_BP_TAGS, "function"),
    ]

    for macro, out_kind, tags, decl_kind in macro_rules:
        for _start, end, specs in collect_macro_invocations(lines, macro):
            if not has_any_tag(specs, tags):
                continue
            name, decl_line, decl = find_next_declaration(lines, end, decl_kind)
            items.append(
                Item(
                    kind=out_kind,
                    name=name,
                    file=str(path.relative_to(root)),
                    line=decl_line,
                    specifiers=specs,
                    declaration=decl,
                )
            )

    return items


def to_markdown(items: list[Item]) -> str:
    order = ["class", "interface", "struct", "enum", "property", "function"]
    grouped: dict[str, list[Item]] = {k: [] for k in order}
    for it in items:
        grouped.setdefault(it.kind, []).append(it)

    out = ["# UE5 Blueprint API Inventory", "", f"Total: {len(items)}", ""]

    for kind in order:
        arr = grouped.get(kind, [])
        out.append(f"## {kind.title()} ({len(arr)})")
        if not arr:
            out.append("_None found._")
            out.append("")
            continue
        out.append("| Name | File | Line | Specifiers | Declaration |")
        out.append("|---|---|---:|---|---|")
        for it in sorted(arr, key=lambda x: (x.file, x.line, x.name)):
            specs = ", ".join(it.specifiers).replace("|", "\\|")
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
        Path(args.json_out).write_text(
            json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.md_out:
        Path(args.md_out).write_text(to_markdown(items), encoding="utf-8")

    if not args.json_out and not args.md_out:
        print(to_markdown(items))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
