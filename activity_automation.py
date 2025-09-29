#!/usr/bin/env python3
"""Automate backfill commits, multi-language PRs, and issue creation."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import random
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import textwrap


class AutomationError(RuntimeError):
    """Raised when the automation cannot proceed."""


@dataclass(frozen=True)
class CodeSnippet:
    branch: str
    path: Path
    content: str
    commit_message: str
    pr_title: str
    pr_body: str
    executable: bool = False


SNIPPETS: tuple[CodeSnippet, ...] = (
    CodeSnippet(
        branch="feature/python-snippet",
        path=Path("snippets/random_tool.py"),
        content=textwrap.dedent(
            """
            \"\"\"Small utility with deterministic pseudo-random output.\"\"\"

            from __future__ import annotations

            import hashlib


            def fingerprint(text: str, length: int = 8) -> str:
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                return digest[:length]


            if __name__ == "__main__":
                print(fingerprint("codex-demo"))
            """
        ).strip()
        + "\n",
        commit_message="Add Python fingerprint helper",
        pr_title="Add Python fingerprint helper",
        pr_body="新增 Python 指纹工具演示。",
    ),
    CodeSnippet(
        branch="feature/js-widget",
        path=Path("web/widget.js"),
        content=textwrap.dedent(
            """
            // Minimal widget helper to format metric displays.
            export function formatMetric(value, unit = '') {
              const rounded = Number.parseFloat(value).toFixed(2);
              return unit ? `${rounded} ${unit}`.trim() : rounded;
            }

            export function buildWidgetConfig(title, value, unit) {
              return {
                title,
                value: formatMetric(value, unit),
                generatedAt: new Date().toISOString(),
              };
            }

            // Emit a demo config when run directly with Node.
            if (import.meta.url === `file://${process.argv[1]}`) {
              console.log(buildWidgetConfig('demo', 42, 'pts'));
            }
            """
        ).strip()
        + "\n",
        commit_message="Add simple JS widget formatter",
        pr_title="Add JS widget formatter",
        pr_body="新增 JS widget 工具演示。",
    ),
    CodeSnippet(
        branch="feature/go-tool",
        path=Path("cmd/randomtool/main.go"),
        content=textwrap.dedent(
            """
            package main

            import (
                "crypto/sha1"
                "encoding/hex"
                "fmt"
                "os"
            )

            func checksum(parts ...string) string {
                h := sha1.New()
                for _, part := range parts {
                    h.Write([]byte(part))
                }
                return hex.EncodeToString(h.Sum(nil))[:12]
            }

            func main() {
                args := os.Args[1:]
                if len(args) == 0 {
                    fmt.Println(checksum("codex", "demo"))
                    return
                }
                fmt.Println(checksum(args...))
            }
            """
        ).strip()
        + "\n",
        commit_message="Add Go checksum demo",
        pr_title="Add Go checksum demo",
        pr_body="新增 Go 校验和示例程序。",
    ),
    CodeSnippet(
        branch="feature/rust-demo",
        path=Path("rust_demo/src/main.rs"),
        content=textwrap.dedent(
            """
            fn banner(message: &str) -> String {
                format!("*** {} ***", message.to_uppercase())
            }

            fn main() {
                println!("{}", banner("codex demo"));
            }

            #[cfg(test)]
            mod tests {
                use super::banner;

                #[test]
                fn banner_wraps_text() {
                    assert_eq!(banner("demo"), "*** DEMO ***");
                }
            }
            """
        ).strip()
        + "\n",
        commit_message="Add Rust banner demo",
        pr_title="Add Rust banner demo",
        pr_body="新增 Rust banner 示例和简单测试。",
    ),
    CodeSnippet(
        branch="feature/java-sample",
        path=Path("java_demo/src/Main.java"),
        content=textwrap.dedent(
            """
            package java_demo;

            import java.time.LocalDateTime;
            import java.time.format.DateTimeFormatter;

            public final class Main {
                private Main() {}

                public static String greeting(String name) {
                    return "Hello, " + name + "!";
                }

                public static void main(String[] args) {
                    var formatter = DateTimeFormatter.ISO_LOCAL_DATE_TIME;
                    var timestamp = LocalDateTime.now().format(formatter);
                    System.out.println(greeting("Codex") + " @ " + timestamp);
                }
            }
            """
        ).strip()
        + "\n",
        commit_message="Add Java greeting sample",
        pr_title="Add Java greeting sample",
        pr_body="新增 Java 问候程序。",
    ),
    CodeSnippet(
        branch="feature/ruby-script",
        path=Path("ruby_scripts/summary.rb"),
        content=textwrap.dedent(
            """
            #!/usr/bin/env ruby
            # frozen_string_literal: true

            def summarize(text)
              counts = Hash.new(0)
              text.split.each { |word| counts[word.downcase] += 1 }
              counts.sort_by { |word, count| [-count, word] }
            end

            if $PROGRAM_NAME == __FILE__
              sample = "Codex codex demo script"
              summarize(sample).each do |word, count|
                puts format("%s => %d", word, count)
              end
            end
            """
        ).strip()
        + "\n",
        commit_message="Add Ruby word summary script",
        pr_title="Add Ruby word summary",
        pr_body="新增 Ruby 脚本统计词频。",
        executable=True,
    ),
    CodeSnippet(
        branch="feature/bash-tool",
        path=Path("scripts/random_report.sh"),
        content=textwrap.dedent(
            """
            #!/usr/bin/env bash
            set -euo pipefail

            project=${1:-sample}
            seed=${2:-$RANDOM}

            hash=$(printf '%s:%s' "$project" "$seed" | shasum | cut -c1-12)
            metric=$((seed % 100 + 1))

            printf 'project=%s\nseed=%s\nhash=%s\nmetric=%s\n' "$project" "$seed" "$hash" "$metric"
            """
        ).strip()
        + "\n",
        commit_message="Add bash random report script",
        pr_title="Add bash random report script",
        pr_body="新增 Bash 随机报告脚本。",
        executable=True,
    ),
)


ISSUES: tuple[tuple[str, str], ...] = (
    ("Document Python fingerprint helper", "补充 Python 指纹工具的使用说明。"),
    ("Add JS widget docs", "撰写 JS widget formatter 的 README 示例。"),
    ("Go checksum tests", "给 Go checksum demo 添加更多单元测试。"),
    ("Rust banner CLI polish", "完善 Rust banner demo 的 CLI 参数体验。"),
    ("Bash report improvements", "优化 Bash 随机报告脚本的输出格式。"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate PR/Issue activity for this repo.")
    parser.add_argument(
        "--years",
        type=str,
        default="2023,2024,2025",
        help="Comma-separated years to backfill (e.g. 2022,2023).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Days per year to backfill.",
    )
    parser.add_argument(
        "--backfill-count",
        type=int,
        default=3,
        help="How many years from --years to process (0 to skip).",
    )
    parser.add_argument(
        "--snippet-count", type=int, default=len(SNIPPETS), help="Number of snippet PRs to create."
    )
    parser.add_argument(
        "--issue-count", type=int, default=len(ISSUES), help="Number of issues to create."
    )
    parser.add_argument("--allow-dirty", action="store_true", help="Proceed even if git status not clean.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def ensure_cli_available(binary: str) -> None:
    if shutil.which(binary) is None:  # type: ignore[name-defined]
        raise AutomationError(f"Required executable '{binary}' not found in PATH.")


try:
    import shutil
except ImportError:  # pragma: no cover
    raise SystemExit("Python standard module 'shutil' is required.")


def run(cmd: Iterable[str], *, capture: bool = False, input_text: str | None = None, dry_run: bool = False) -> str:
    text = " ".join(shlex.quote(part) for part in cmd)
    print(f"$ {text}")
    if dry_run:
        return ""
    result = subprocess.run(
        list(cmd),
        check=True,
        text=True,
        capture_output=capture,
        input=input_text,
    )
    if capture:
        return result.stdout.strip()
    return ""


def ensure_clean(allow_dirty: bool, dry_run: bool) -> None:
    status = run(["git", "status", "--porcelain"], capture=True, dry_run=dry_run)
    if dry_run:
        print("[dry-run] skipping clean check")
        return
    if status.strip() and not allow_dirty:
        raise AutomationError("Working tree not clean. Commit/stash changes or pass --allow-dirty.")


def current_date_iso() -> dt.date:
    return dt.datetime.now().date()


def compute_year_range(year: int) -> tuple[str, str]:
    start = dt.date(year, 1, 1)
    today = current_date_iso()
    if year >= today.year:
        end = today - dt.timedelta(days=1)
    else:
        end = dt.date(year, 12, 31)
    if end < start:
        raise AutomationError(f"No valid range for year {year}; end precedes start.")
    return start.isoformat(), end.isoformat()


def backfill_year(year: int, sample_size: int, dry_run: bool) -> tuple[str, str, str]:
    start, end = compute_year_range(year)
    branch = f"backfill/{year}-activity"
    seed = year

    if dry_run:
        print(f"[dry-run] would backfill {sample_size} days for {year} on {branch}")
        return branch, "", ""

    module = importlib.import_module("backfill_commits")
    module = importlib.reload(module)

    original_plan = module.plan_commits_per_day

    def sampled_plan(dates: list[dt.date], min_commits: int, max_commits: int) -> dict[dt.date, int]:
        if len(dates) < sample_size:
            raise AutomationError(f"Year {year} range has only {len(dates)} days; need {sample_size}.")
        rng = random.Random(seed)
        chosen = set(rng.sample(dates, sample_size))
        return {day: (1 if day in chosen else 0) for day in dates}

    module.plan_commits_per_day = sampled_plan

    argv_backup = list(sys.argv)
    sys.argv = [
        "backfill_commits.py",
        "--branch",
        branch,
        "--start",
        start,
        "--end",
        end,
        "--per-day-min",
        "1",
        "--per-day-max",
        "1",
    ]

    try:
        module.main()
    finally:
        module.plan_commits_per_day = original_plan
        sys.argv = argv_backup

    push_output = run(["git", "push", "-u", "origin", branch])
    pr_url = create_pr(
        title=f"Backfill {year} activity",
        body=f"为 {year} 年随机 {sample_size} 天补充 keep.log 记录。",
        head=branch,
        dry_run=dry_run,
    )
    pr_number = extract_pr_number(pr_url)
    finalize_pr(pr_number, method="merge", dry_run=dry_run)
    return branch, pr_url, push_output or ""


def create_pr(*, title: str, body: str, head: str, dry_run: bool) -> str:
    if dry_run:
        print(f"[dry-run] would open PR '{title}' from {head}")
        return ""
    output = run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            "main",
            "--head",
            head,
        ],
        capture=True,
    )
    return output


def extract_pr_number(pr_url: str) -> str:
    match = re.search(r"/pull/(\d+)", pr_url)
    if not match:
        raise AutomationError(f"Unable to parse PR number from: {pr_url}")
    return match.group(1)


def finalize_pr(pr_number: str, *, method: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] would merge PR #{pr_number}")
        return
    run(["git", "checkout", "main"])
    run(["git", "pull", "--ff-only", "origin", "main"])
    flags = {
        "merge": "--merge",
        "squash": "--squash",
    }
    flag = flags.get(method, "--merge")
    run(
        ["gh", "pr", "merge", pr_number, flag, "--delete-branch"],
        input_text="y\n",
    )
    run(["git", "pull", "--ff-only", "origin", "main"])


def apply_snippet(snippet: CodeSnippet, dry_run: bool) -> str:
    branch = snippet.branch
    if dry_run:
        print(f"[dry-run] would create PR for {branch}")
        return ""

    run(["git", "checkout", "main"])
    run(["git", "checkout", "-b", branch])
    snippet.path.parent.mkdir(parents=True, exist_ok=True)
    snippet.path.write_text(snippet.content, encoding="utf-8")
    if snippet.executable:
        snippet.path.chmod(0o755)
    run(["git", "add", str(snippet.path)])
    run(["git", "commit", "-m", snippet.commit_message])
    run(["git", "push", "-u", "origin", branch])
    pr_url = create_pr(title=snippet.pr_title, body=snippet.pr_body, head=branch, dry_run=dry_run)
    pr_number = extract_pr_number(pr_url)
    finalize_pr(pr_number, method="squash", dry_run=dry_run)
    return pr_url


def create_issue(title: str, body: str, dry_run: bool) -> str:
    if dry_run:
        print(f"[dry-run] would open issue '{title}'")
        return ""
    output = run([
        "gh",
        "issue",
        "create",
        "--title",
        title,
        "--body",
        body,
    ], capture=True)
    return output


def main() -> None:
    args = parse_args()
    ensure_cli_available("git")
    ensure_cli_available("gh")

    repo_root = Path.cwd()
    if not (repo_root / ".git").exists():
        raise AutomationError("Run this script from the repository root.")

    ensure_clean(args.allow_dirty, args.dry_run)

    years = [int(part.strip()) for part in args.years.split(",") if part.strip()]
    summary: dict[str, list[str]] = {"prs": [], "issues": []}

    if args.backfill_count > 0:
        if args.backfill_count > len(years):
            raise AutomationError("--backfill-count exceeds number of parsed years.")
        for year in years[: args.backfill_count]:
            pr = backfill_year(year, args.sample_size, args.dry_run)
            summary["prs"].append(pr[1])

    if args.snippet_count > 0:
        for snippet in SNIPPETS[: args.snippet_count]:
            pr_url = apply_snippet(snippet, args.dry_run)
            summary["prs"].append(pr_url)

    if args.issue_count > 0:
        if args.issue_count > len(ISSUES):
            raise AutomationError("--issue-count exceeds available issue templates.")
        for title, body in ISSUES[: args.issue_count]:
            issue_url = create_issue(title, body, args.dry_run)
            summary["issues"].append(issue_url)

    print("Automation complete.")
    for pr in filter(None, summary["prs"]):
        print(f"  PR: {pr}")
    for issue in filter(None, summary["issues"]):
        print(f"  Issue: {issue}")


if __name__ == "__main__":
    try:
        main()
    except AutomationError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as error:
        print(f"Command failed: {error}", file=sys.stderr)
        sys.exit(error.returncode)
