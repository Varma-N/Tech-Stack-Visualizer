#!/usr/bin/env python3
"""
generate_tech_stack.py

Generates three SVG README cards (Top-5 languages, GitHub basic stats, All languages list)
and writes them to assets/<USERNAME>_*.svg

Usage:
  - Provide secrets in GitHub Actions as:
      USERNAME -> your GitHub username
      TOKEN    -> optional Personal Access Token (recommended for higher rate limits)
  - Or run locally:
      export USERNAME=yourname
      export TOKEN=ghp_xxx   # optional
      python src/generate_tech_stack.py

Notes:
  - This script focuses on public repos when no token is provided.
  - It uses the GitHub REST API (v3). Rate-limits may apply if you do many runs without a token.
"""
from __future__ import annotations
import os
import sys
import math
import time
import requests
from datetime import datetime
from typing import Dict, List, Tuple

# ---------- Config ----------
API_BASE = "https://api.github.com"
OUTPUT_DIR = "assets"
CARD_WIDTH = 500  # px (locked as requested)
FONT_FAMILY = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
DARK_BG = "#0d1117"
TITLE_COLOR = "#539bf5"
TEXT_COLOR = "#e6edf3"
TRACK_COLOR = "#30363d"
PALETTE = ["#6EE7B7", "#FDE68A", "#A78BFA", "#FCA5A5", "#60A5FA", "#F59E0B", "#34D399", "#F472B6"]

# ---------- Helpers: HTTP ----------
def gh_get(path: str, token: str | None = None, params: dict | None = None, accept: str | None = None):
    url = f"{API_BASE}{path}"
    headers = {"Accept": accept or "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(url, headers=headers, params=params or {})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp

# ---------- Fetching repos & languages ----------
def fetch_all_repos(username: str, token: str | None) -> List[dict]:
    repos = []
    page = 1
    per_page = 100
    while True:
        params = {"per_page": per_page, "page": page, "type": "owner", "sort": "updated"}
        resp = gh_get(f"/users/{username}/repos", token, params=params)
        data = resp.json()
        repos.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return repos

def fetch_repo_languages(owner: str, repo: str, token: str | None) -> Dict[str, int]:
    resp = gh_get(f"/repos/{owner}/{repo}/languages", token)
    return resp.json() if resp is not None else {}

# ---------- Stats computations ----------
def aggregate_languages(repos: List[dict], token: str | None) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for r in repos:
        owner = r["owner"]["login"]
        name = r["name"]
        try:
            langs = fetch_repo_languages(owner, name, token)
        except Exception as e:
            print(f"Warning: failed to fetch languages for {name}: {e}", file=sys.stderr)
            continue
        for lang, b in langs.items():
            totals[lang] = totals.get(lang, 0) + b
    return totals

def compute_percentages(totals: Dict[str, int]) -> List[Tuple[str, float, int]]:
    total_bytes = sum(totals.values())
    if total_bytes == 0:
        return []
    items = [(lang, (bytes_count / total_bytes) * 100.0, bytes_count) for lang, bytes_count in totals.items()]
    items.sort(key=lambda x: x[2], reverse=True)
    return items

def get_top_n(items: List[Tuple[str, float, int]], n: int) -> List[Tuple[str, float, int]]:
    return items[:n]

# ---------- GitHub basic stats ----------
def total_stars(repos: List[dict]) -> int:
    return sum(r.get("stargazers_count", 0) for r in repos)

def count_commits_since(repos: List[dict], username: str, since_iso: str, token: str | None) -> int:
    """
    Count commits in each repo since `since_iso` by using per_page=1 and parsing Link header.
    Per-repo approach to sum commits authored in that repo (commits API counts all commits, not just authored by username).
    This uses commits endpoint without author filter for simplicity (counts all commits in repo).
    """
    total = 0
    for r in repos:
        owner = r["owner"]["login"]
        repo = r["name"]
        try:
            params = {"since": since_iso, "per_page": 1}
            resp = gh_get(f"/repos/{owner}/{repo}/commits", token, params=params)
            if resp is None:
                continue
            if "Link" in resp.headers:
                link = resp.headers["Link"]
                # find last page number
                # example: <https://api.github.com/.../commits?since=...&per_page=1&page=23>; rel="last", ...
                import re
                m = re.search(r'[&?]page=(\d+)>; rel="last"', link)
                if m:
                    total += int(m.group(1))
                else:
                    # fallback: count returned items
                    total += len(resp.json())
            else:
                total += len(resp.json())
        except Exception:
            # ignore per-repo errors
            continue
    return total

def search_count(query: str, token: str | None, accept_preview: bool = False) -> int:
    headers_accept = "application/vnd.github.v3+json"
    if accept_preview:
        headers_accept = "application/vnd.github.cloak-preview"
    params = {"q": query, "per_page": 1}
    resp = gh_get("/search/issues", token, params=params, accept=headers_accept)
    if resp is None:
        return 0
    data = resp.json()
    return data.get("total_count", 0)

def count_prs(username: str, year: int, token: str | None) -> int:
    # PRs authored by username during year across all repos
    since = f"{year}-01-01"
    until = f"{year}-12-31"
    q = f"type:pr+author:{username}+created:{since}..{until}"
    return search_count(q, token)

def count_issues(username: str, year: int, token: str | None) -> int:
    since = f"{year}-01-01"
    until = f"{year}-12-31"
    q = f"type:issue+author:{username}+created:{since}..{until}"
    return search_count(q, token)

def count_contributed_repos(repos: List[dict], username: str, token: str | None) -> int:
    count = 0
    for r in repos:
        owner = r["owner"]["login"]
        name = r["name"]
        try:
            resp = gh_get(f"/repos/{owner}/{name}/contributors", token, params={"per_page": 100})
            if resp is None:
                continue
            contribs = resp.json()
            for c in contribs:
                if c.get("login", "").lower() == username.lower():
                    count += 1
                    break
        except Exception:
            continue
    return count

# ---------- Simple grading for circle badge ----------
def build_grade(stars: int, commits: int, prs: int, issues: int, contribs: int) -> str:
    # Heuristic score -> grade
    score = 0.0
    score += min(stars / 50.0, 1.0) * 40  # stars up to 50 contribute 40
    score += min(commits / 200.0, 1.0) * 25
    score += min(prs / 20.0, 1.0) * 15
    score += min(contribs / 10.0, 1.0) * 15
    # issues not directly positive; small boost
    score += min(issues / 30.0, 1.0) * 5
    # map to grades
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B+"
    if score >= 60:
        return "B"
    if score >= 50:
        return "C+"
    return "C"

# ---------- SVG generation helpers ----------
def px(n: int) -> str:
    return f"{n}px"

def svg_text(x, y, content, size=14, weight=400, color=TEXT_COLOR, anchor="start"):
    return f'<text x="{x}" y="{y}" font-family={FONT_FAMILY!s} font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{content}</text>'

def write_file(path: str, data: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)

# ---------- Card 1: Top-5 languages with rounded bars ----------
def render_top_languages_card(username: str, items: List[Tuple[str, float, int]], out_path: str):
    # items: list of (lang, pct, bytes)
    top = items[:5]
    rows = len(top)
    width = CARD_WIDTH
    padding_x = 20
    padding_y_top = 28
    row_h = 34  # vertical space per row
    title_h = 28
    height = padding_y_top + title_h + 12 + rows * row_h + 20

    bar_x = padding_x + 130  # start of bar
    bar_w = width - bar_x - padding_x - 60  # leave space for percentage text
    bar_h = 10

    svg = []
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<rect rx="12" ry="12" width="100%" height="100%" fill="{DARK_BG}" />')
    # Title
    svg.append(f'<text x="{padding_x}" y="{padding_y_top}" font-family={FONT_FAMILY!s} font-size="20" font-weight="700" fill="{TITLE_COLOR}">Most Used Languages</text>')

    y0 = padding_y_top + 20
    for i, (lang, pct, _) in enumerate(top):
        y = y0 + 10 + i * row_h
        # language label
        svg.append(f'<text x="{padding_x}" y="{y}" font-family={FONT_FAMILY!s} font-size="13" font-weight="600" fill="{TEXT_COLOR}">{lang}</text>')
        # track
        track_x = bar_x
        track_y = y - 10
        svg.append(f'<rect x="{track_x}" y="{track_y}" rx="{bar_h/2}" ry="{bar_h/2}" width="{bar_w}" height="{bar_h}" fill="{TRACK_COLOR}" />')
        # filled bar
        pct_clamped = max(0.0, min(100.0, pct))
        fill_w = (pct_clamped / 100.0) * bar_w
        color = PALETTE[i % len(PALETTE)]
        svg.append(f'<rect x="{track_x}" y="{track_y}" rx="{bar_h/2}" ry="{bar_h/2}" width="{fill_w}" height="{bar_h}" fill="{color}" />')
        # percentage text (right)
        pct_text = f"{pct_clamped:.2f}%"
        svg.append(f'<text x="{track_x + bar_w + 8}" y="{y}" font-family={FONT_FAMILY!s} font-size="13" font-weight="600" fill="{TEXT_COLOR}">{pct_text}</text>')
    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))

# ---------- Card 2: GitHub Stats ----------
def render_github_stats_card(username: str, stars: int, commits: int, prs: int, issues: int, contribs: int, out_path: str):
    width = CARD_WIDTH
    padding_x = 20
    padding_y = 24
    line_h = 34
    title_h = 26
    rows = 5
    height = padding_y + title_h + 12 + rows * line_h + 20

    svg = []
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<rect rx="12" ry="12" width="100%" height="100%" fill="{DARK_BG}" />')
    svg.append(f'<text x="{padding_x}" y="{padding_y}" font-family={FONT_FAMILY!s} font-size="20" font-weight="700" fill="{TITLE_COLOR}">GitHub Stats</text>')

    y0 = padding_y + 24
    labels = [
        ("★ Stars", str(stars)),
        ("🔁 Commits (this year)", str(commits)),
        ("🔀 Pull Requests", str(prs)),
        ("🐞 Issues", str(issues)),
        ("🧩 Contributed repos", str(contribs)),
    ]
    for i, (label, value) in enumerate(labels):
        y = y0 + i * line_h
        svg.append(f'<text x="{padding_x}" y="{y}" font-family={FONT_FAMILY!s} font-size="13" font-weight="600" fill="{TEXT_COLOR}">{label}</text>')
        svg.append(f'<text x="{width - padding_x - 12}" y="{y}" font-family={FONT_FAMILY!s} font-size="13" font-weight="700" fill="{TEXT_COLOR}" text-anchor="end">{value}</text>')

    # grade circle at right middle
    grade = build_grade(stars, commits, prs, issues, contribs)
    circ_cx = width - 70
    circ_cy = y0 + (rows * line_h) / 2 - 8
    svg.append(f'<circle cx="{circ_cx}" cy="{circ_cy}" r="32" stroke="#2b6cb0" stroke-width="6" fill="none" opacity="0.18" />')
    svg.append(f'<text x="{circ_cx}" y="{circ_cy + 6}" font-family={FONT_FAMILY!s} font-size="20" font-weight="800" fill="{TITLE_COLOR}" text-anchor="middle">{grade}</text>')

    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))

# ---------- Card 3: All languages two-column list ----------
def render_languages_list_card(username: str, items: List[Tuple[str, float, int]], out_path: str):
    # items has all languages sorted by bytes desc
    # two columns
    cols = 2
    per_col = (len(items) + cols - 1) // cols
    width = CARD_WIDTH
    padding_x = 20
    padding_y_top = 28
    title_h = 28
    row_h = 22
    height = padding_y_top + title_h + 12 + per_col * row_h + 22

    svg = []
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<rect rx="12" ry="12" width="100%" height="100%" fill="{DARK_BG}" />')
    svg.append(f'<text x="{padding_x}" y="{padding_y_top}" font-family={FONT_FAMILY!s} font-size="20" font-weight="700" fill="{TITLE_COLOR}">Languages Breakdown</text>')

    start_y = padding_y_top + 22
    col_x = [padding_x, width / 2 + 10]
    dot_r = 6
    for idx, (lang, pct, _) in enumerate(items):
        col = 0 if idx < per_col else 1
        row = idx if col == 0 else idx - per_col
        x = col_x[col]
        y = start_y + row * row_h
        color = PALETTE[idx % len(PALETTE)]
        # circle
        svg.append(f'<circle cx="{x+6}" cy="{y-6}" r="{dot_r}" fill="{color}" />')
        # label
        svg.append(f'<text x="{x+20}" y="{y-2}" font-family={FONT_FAMILY!s} font-size="12" font-weight="600" fill="{TEXT_COLOR}">{lang}</text>')
        svg.append(f'<text x="{x + (width/2 - padding_x) - 6}" y="{y-2}" font-family={FONT_FAMILY!s} font-size="12" font-weight="600" fill="{TEXT_COLOR}" text-anchor="end">{pct:.2f}%</text>')

    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))

# ---------- Main flow ----------
def main():
    username = os.environ.get("USERNAME") or os.environ.get("GITHUB_USERNAME")
    token = os.environ.get("TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not username:
        print("Error: set USERNAME environment variable (or GITHUB_USERNAME).", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching repos for user: {username} ...")
    repos = fetch_all_repos(username, token)
    print(f"Found {len(repos)} repos.")

    totals = aggregate_languages(repos, token)
    items = compute_percentages(totals)  # list of (lang, pct, bytes)
    if not items:
        print("No language data found.")
    else:
        # Top 5 card
        top5 = get_top_n(items, 5)
        top_card_path = os.path.join(OUTPUT_DIR, f"{username}_top_languages_card.svg")
        render_top_languages_card(username, top5, top_card_path)
        print("Wrote:", top_card_path)

        # All languages list card
        list_card_path = os.path.join(OUTPUT_DIR, f"{username}_languages_list_card.svg")
        render_languages_list_card(username, items, list_card_path)
        print("Wrote:", list_card_path)

    # GitHub Stats
    stars = total_stars(repos)
    this_year = datetime.utcnow().year
    since_iso = f"{this_year}-01-01T00:00:00Z"
    commits = count_commits_since(repos, username, since_iso, token)
    prs = count_prs(username, this_year, token)
    issues = count_issues(username, this_year, token)
    contribs = count_contributed_repos(repos, username, token)

    stats_card_path = os.path.join(OUTPUT_DIR, f"{username}_github_stats_card.svg")
    render_github_stats_card(username, stars, commits, prs, issues, contribs, stats_card_path)
    print("Wrote:", stats_card_path)

if __name__ == "__main__":
    main()
