"""Fail CI when changed Python code introduces silent exception swallowing.

Inspired by the MIT-licensed ECC silent-failure-hunter review discipline:
https://github.com/affaan-m/ECC

This is intentionally a narrow ARENA-native gate, not a vendored ECC agent.
It checks only Python files changed against the PR base (or HEAD^ on push), so
legacy code is not grandfathered into a fake "clean" claim and unrelated code
is not rewritten merely to adopt the gate.
"""
from __future__ import annotations

import argparse
import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    detail: str


def changed_python_files(base: str | None = None) -> list[Path]:
    if base:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"]
    else:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD^", "HEAD"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [
        Path(line)
        for line in result.stdout.splitlines()
        if line.endswith(".py") and Path(line).is_file()
    ]


def inspect_source(source: str, path: str = "<memory>") -> list[Finding]:
    tree = ast.parse(source, filename=path)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            findings.append(Finding(path, node.lineno, "ARENA-SF001", "bare except"))
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            findings.append(
                Finding(path, node.lineno, "ARENA-SF002", "exception swallowed with pass")
            )
    return findings


def inspect_files(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        try:
            findings.extend(inspect_source(path.read_text(encoding="utf-8"), str(path)))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(Finding(str(path), 1, "ARENA-SF000", f"cannot inspect: {exc}"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="ARENA changed-code silent-failure gate")
    parser.add_argument("--base", help="Git base ref/sha; defaults to HEAD^")
    parser.add_argument("paths", nargs="*", type=Path, help="Explicit Python files (tests/local use)")
    args = parser.parse_args()
    paths = args.paths or changed_python_files(args.base)
    findings = inspect_files(paths)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule} {finding.detail}")
    if findings:
        print(f"silent-failure gate: {len(findings)} finding(s)")
        return 1
    print(f"silent-failure gate: clean ({len(paths)} changed Python file(s) inspected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
