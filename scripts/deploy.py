from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
TEMPLATES_DIR = ROOT / "templates"
MANIFEST_PATH = ROOT / "data" / "render_manifest.json"

REPORT_LIST_PATTERN = re.compile(
    r"(<div id=\"reportList\">\s*)(.*?)(\s*</div>\s*</div>\s*<!-- FOOTER -->)",
    re.DOTALL,
)
CARD_PATTERN = re.compile(r"\s*<a class=\"report-card.*?</a>\s*", re.DOTALL)
HREF_PATTERN = re.compile(r'href="([^"]+)"')
STAT_REPORTS_PATTERN = re.compile(r'(<div class="stat-num" id="statReports">)(\d+)(</div>)')
REPORT_COUNT_PATTERN = re.compile(r'(<span class="count" id="reportCount">)(\d+)개(</span>)')


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("Missing data/render_manifest.json. Run generate_briefing.py first.")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def render_card(context: dict[str, Any]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    template = env.get_template("card.html.j2")
    return template.render(**context).strip()


def clean_existing_cards(html_text: str, target_href: str) -> list[str]:
    cards = CARD_PATTERN.findall(html_text)
    cleaned: list[str] = []
    for card in cards:
        href_match = HREF_PATTERN.search(card)
        href = href_match.group(1) if href_match else ""
        if href == target_href:
            continue
        updated = card.replace(" latest", "")
        updated = re.sub(r"\s*<span class=\"rc-badge new\">NEW</span>\n?", "\n", updated)
        cleaned.append(updated.strip())
    return cleaned


def update_index(context: dict[str, Any]) -> int:
    original = INDEX_PATH.read_text(encoding="utf-8")
    match = REPORT_LIST_PATTERN.search(original)
    if not match:
        raise RuntimeError("Could not find <div id='reportList'> insertion target in index.html")

    before, inner, after = match.groups()
    cards = clean_existing_cards(inner, context["href"])
    cards.insert(0, render_card(context))
    joined_cards = "\n\n".join(cards)
    updated = original[: match.start()] + before + "\n\n" + joined_cards + "\n\n    " + after + original[match.end() :]

    total_reports = len(cards)
    updated = STAT_REPORTS_PATTERN.sub(rf"\g<1>{total_reports}\g<3>", updated, count=1)
    updated = REPORT_COUNT_PATTERN.sub(rf"\g<1>{total_reports}개\g<3>", updated, count=1)
    INDEX_PATH.write_text(updated, encoding="utf-8")
    return total_reports


def run_git(args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def create_commit(date_str: str, push: bool) -> None:
    run_git(["add", "index.html", f"briefing-{date_str}.html"])
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT,
        check=False,
    )
    if diff.returncode == 0:
        print("No staged changes to commit.")
        return
    run_git(["commit", "-m", f"배포: {date_str} 브리핑 자동 생성"])
    if push:
        run_git(["push", "origin", "main"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--no-push", action="store_true", help="Commit locally without pushing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = load_manifest()
    if context["href"] != f"briefing-{args.date}.html":
        raise RuntimeError("Manifest date does not match --date argument.")

    total_reports = update_index(context)
    create_commit(args.date, push=not args.no_push)
    cache_buster = datetime.fromisoformat(args.date).strftime("%Y%m%d")
    print(f"Updated archive count: {total_reports}")
    print(f"Success URL: https://aisyncclub.github.io/moneyclub/?r={cache_buster}")


if __name__ == "__main__":
    main()
