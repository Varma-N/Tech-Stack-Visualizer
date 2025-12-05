#!/usr/bin/env python3

from __future__ import annotations
import os
import sys
import math
import requests
from datetime import datetime
from typing import Dict, List, Tuple

# ----------------------------------------------------
# GLOBAL CONFIG
# ----------------------------------------------------
API_BASE = "https://api.github.com"
OUTPUT_DIR = "assets"
CARD_WIDTH = 500
FONT_FAMILY = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'

DARK_BG = "#0d1117"
TITLE_COLOR = "#539bf5"
TEXT_COLOR = "#e6edf3"
TRACK_COLOR = "#30363d"

PALETTE = ["#6EE7B7", "#FDE68A", "#A78BFA", "#FCA5A5",
           "#60A5FA", "#F59E0B", "#34D399", "#F472B6"]


# ----------------------------------------------------
# HTTP WRAPPER WITH FALLBACK LOGIC
# ----------------------------------------------------
class TokenInvalid(Exception):
    pass


def gh_get(path: str, token: str | None, params=None, accept=None, fallback_allowed=True):
    url = f"{API_BASE}{path}"
    headers = {"Accept": accept or "application/vnd.github.v3+json"}

    if token:
        headers["Authorization"] = f"token {token}"

    resp = requests.get(url, headers=headers, params=params or {})

    if resp.status_code == 401 and fallback_allowed:
        print("Token invalid or expired → fallback to public mode.")
        raise TokenInvalid

    resp.raise_for_status()
    return resp


# ----------------------------------------------------
# REPO FETCHING (PRIVATE → PUBLIC FALLBACK)
# ----------------------------------------------------
def fetch_repos_dynamic(username: str, token: str | None) -> List[dict]:
    if token:
        try:
            print("Fetching repos with token (private + public)...")
            repos = []
            page = 1
            while True:
                resp = gh_get("/user/repos", token, params={"per_page": 100, "page": page})
                data = resp.json()
                repos.extend(data)
                if len(data) < 100:
                    break
                page += 1
            return repos
        except TokenInvalid:
            print("Falling back to public repos only...")
            token = None

    repos = []
    page = 1
    while True:
        resp = gh_get(f"/users/{username}/repos", None, params={"per_page": 100, "page": page})
        data = resp.json()
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


# ----------------------------------------------------
# LANGUAGE AGGREGATION
# ----------------------------------------------------
def fetch_repo_languages(owner: str, repo: str, token: str | None):
    try:
        return gh_get(f"/repos/{owner}/{repo}/languages", token).json()
    except TokenInvalid:
        return gh_get(f"/repos/{owner}/{repo}/languages", None).json()


def aggregate_languages(repos: List[dict], token: str | None):
    totals = {}
    for r in repos:
        owner = r["owner"]["login"]
        name = r["name"]
        try:
            langs = fetch_repo_languages(owner, name, token)
        except Exception:
            continue

        for lang, b in langs.items():
            totals[lang] = totals.get(lang, 0) + b

    return totals


def compute_percentages(totals: Dict[str, int]):
    total_bytes = sum(totals.values())
    if total_bytes == 0:
        return []

    items = [(lang, (bytes_val / total_bytes) * 100.0, bytes_val)
             for lang, bytes_val in totals.items()]

    items.sort(key=lambda x: x[2], reverse=True)
    return items


# ----------------------------------------------------
# GITHUB SEARCH API HELPERS (PRs, Issues)
# ----------------------------------------------------
def search_count(query: str, token: str | None):
    try:
        resp = gh_get("/search/issues", token, params={"q": query})
        return resp.json().get("total_count", 0)
    except TokenInvalid:
        resp = gh_get("/search/issues", None, params={"q": query})
        return resp.json().get("total_count", 0)


def count_prs(username: str, year: int, token: str | None):
    q = f"type:pr author:{username} created:{year}-01-01..{year}-12-31"
    return search_count(q, token)


def count_issues(username: str, year: int, token: str | None):
    q = f"type:issue author:{username} created:{year}-01-01..{year}-12-31"
    return search_count(q, token)


# ----------------------------------------------------
# CONTRIBUTED REPOS
# ----------------------------------------------------
def count_contributed_repos(repos: List[dict], username: str, token: str | None):
    count = 0
    for r in repos:
        owner = r["owner"]["login"]
        name = r["name"]

        try:
            resp = gh_get(f"/repos/{owner}/{name}/contributors", token, params={"per_page": 100})
        except TokenInvalid:
            resp = gh_get(f"/repos/{owner}/{name}/contributors", None, params={"per_page": 100})

        data = resp.json()
        if any(c.get("login", "").lower() == username.lower() for c in data):
            count += 1

    return count


# ----------------------------------------------------
# COMMIT COUNT
# ----------------------------------------------------
def count_commits_in_year(repos: List[dict], username: str, token: str | None):
    year = min(datetime.utcnow().year, 2024)
    since_iso = f"{year}-01-01T00:00:00Z"
    total = 0

    for r in repos:
        owner = r["owner"]["login"]
        name = r["name"]

        try:
            resp = gh_get(f"/repos/{owner}/{name}/commits", token,
                          params={"since": since_iso, "per_page": 1})
        except TokenInvalid:
            resp = gh_get(f"/repos/{owner}/{name}/commits", None,
                          params={"since": since_iso, "per_page": 1})

        if "Link" in resp.headers:
            import re
            m = re.search(r'&page=(\d+)>; rel="last"', resp.headers["Link"])
            total += int(m.group(1)) if m else len(resp.json())
        else:
            total += len(resp.json())

    return total


# ----------------------------------------------------
# SVG HELPERS
# ----------------------------------------------------
def write_file(path: str, data: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)


def svg_text(x, y, content, size=14, weight=400, color=TEXT_COLOR, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family={FONT_FAMILY} '
            f'font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}">{content}</text>')


# ----------------------------------------------------
# CARD 1 — TOP 5 LANGUAGES (PROGRESS BARS)
# ----------------------------------------------------
def render_top_languages_card(username: str, items, out_path):
    top = items[:5]
    rows = len(top)

    width = CARD_WIDTH
    padding = 20
    title_y = 32
    row_h = 34
    bar_h = 10

    bar_x = padding + 130
    bar_w = width - bar_x - padding - 60

    height = padding + title_y + rows * row_h + 50

    svg = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="100%" height="100%" rx="12" fill="{DARK_BG}"/>')

    svg.append(svg_text(padding, title_y, "Most Used Languages", 20, 700, TITLE_COLOR))

    y0 = title_y + 22

    for i, (lang, pct, _) in enumerate(top):
        y = y0 + i * row_h

        svg.append(svg_text(padding, y, lang, 13, 600))

        track_y = y - 10
        svg.append(f'<rect x="{bar_x}" y="{track_y}" width="{bar_w}" height="{bar_h}" rx="5" fill="{TRACK_COLOR}"/>')

        fill_w = (pct / 100) * bar_w
        svg.append(f'<rect x="{bar_x}" y="{track_y}" width="{fill_w}" height="{bar_h}" '
                   f'rx="5" fill="{PALETTE[i % len(PALETTE)]}"/>')

        svg.append(svg_text(bar_x + bar_w + 8, y, f"{pct:.2f}%", 13, 600))

    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))


# ----------------------------------------------------
# CARD 2 — GITHUB STATS CARD
# ----------------------------------------------------
def build_grade(stars, commits, prs, issues, contribs):
    score = 0
    score += min(stars / 50, 1) * 40
    score += min(commits / 200, 1) * 25
    score += min(prs / 20, 1) * 15
    score += min(contribs / 10, 1) * 15
    score += min(issues / 30, 1) * 5

    if score >= 90: return "A+"
    if score >= 80: return "A"
    if score >= 70: return "B+"
    if score >= 60: return "B"
    if score >= 50: return "C+"
    return "C"


def render_github_stats_card(username, stars, commits, prs, issues, contribs, out_path):
    width = CARD_WIDTH
    padding = 20
    line_h = 34
    title_y = 32

    rows = [
        ("★ Stars", stars),
        ("🔁 Commits (this year)", commits),
        ("🔀 Pull Requests", prs),
        ("🐞 Issues", issues),
        ("🧩 Contributed repos", contribs),
    ]

    height = padding + title_y + len(rows) * line_h + 50

    svg = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="100%" height="100%" rx="12" fill="{DARK_BG}"/>')
    svg.append(svg_text(padding, title_y, "GitHub Stats", 20, 700, TITLE_COLOR))

    base_y = title_y + 24

    for i, (label, val) in enumerate(rows):
        y = base_y + i * line_h
        svg.append(svg_text(padding, y, label, 13, 600))
        svg.append(svg_text(width - padding, y, str(val), 13, 700, anchor="end"))

    grade = build_grade(stars, commits, prs, issues, contribs)
    cx = width - 70
    cy = base_y + (len(rows) * line_h) / 2 - 8

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="32" stroke="#2b6cb0" stroke-width="6" '
               f'fill="none" opacity="0.18"/>')
    svg.append(svg_text(cx, cy + 6, grade, 20, 800, TITLE_COLOR, anchor="middle"))

    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))


# ----------------------------------------------------
# CARD 3 — FULL LANGUAGE LIST (2 COLUMNS)
# ----------------------------------------------------
def render_languages_list_card(username, items, out_path):
    padding = 20
    title_y = 32
    row_h = 24

    cols = 2
    per_col = (len(items) + 1) // 2

    height = padding + title_y + per_col * row_h + 50
    width = CARD_WIDTH

    svg = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="100%" height="100%" rx="12" fill="{DARK_BG}"/>')
    svg.append(svg_text(padding, title_y, "Languages Breakdown", 20, 700, TITLE_COLOR))

    col_x = [padding, width // 2 + 10]
    start_y = title_y + 22

    for idx, (lang, pct, _) in enumerate(items):
        col = 0 if idx < per_col else 1
        row = idx if col == 0 else idx - per_col

        x = col_x[col]
        y = start_y + row * row_h

        color = PALETTE[idx % len(PALETTE)]
        svg.append(f'<circle cx="{x+6}" cy="{y-6}" r="5" fill="{color}"/>')
        svg.append(svg_text(x + 20, y - 2, lang, 12, 600))
        svg.append(svg_text(x + (width // 2 - padding) - 6, y - 2, f"{pct:.2f}%", 12, 600, anchor="end"))

    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))


# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    username = os.environ.get("USERNAME")
    token = os.environ.get("TOKEN")

    if not username:
        print("Error: USERNAME not set.")
        sys.exit(1)

    repos = fetch_repos_dynamic(username, token)
    print(f"Found {len(repos)} repos.")

    totals = aggregate_languages(repos, token)
    items = compute_percentages(totals)

    if items:
        render_top_languages_card(username, items, f"{OUTPUT_DIR}/{username}_top_languages_card.svg")
        render_languages_list_card(username, items, f"{OUTPUT_DIR}/{username}_languages_list_card.svg")

    # Stats year (GitHub rejects future years)
    year = min(datetime.utcnow().year, 2024)

    stars = count_stars(repos)
    commits = count_commits_in_year(repos, username, token)
    prs = count_prs(username, year, token)
    issues = count_issues(username, year, token)
    contribs = count_contributed_repos(repos, username, token)

    render_github_stats_card(
        username, stars, commits, prs, issues, contribs,
        f"{OUTPUT_DIR}/{username}_github_stats_card.svg"
    )


if __name__ == "__main__":
    main()
