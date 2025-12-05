#!/usr/bin/env python3
"""
generate_tech_stack.py

Tech Stack Visualizer - Option 2 theme (gradient/neon), generate three SVG cards:
 - assets/card_languages_overall.svg   (global distribution small legend)
 - assets/card_languages_top5.svg      (top 5 languages with bars)
 - assets/card_github_stats.svg        (GitHub stats card with circle grade)

Usage:
  python generate_tech_stack.py --username your_github_username
  # optionally provide token: --token YOUR_TOKEN  (or set env GITHUB_TOKEN)
  # set --output-dir to change output folder (default assets)
"""

from __future__ import annotations
import os
import sys
import argparse
import requests
from collections import defaultdict, OrderedDict
from datetime import datetime
import math
import html

GITHUB_API_BASE = "https://api.github.com"

# Visual constants
SVG_WIDTH = 500  # px (as requested)
CARD_PADDING = 20
CARD_RADIUS = 12
BG_COLOR = "#0b0f17"         # dark outer background (page BG)
CARD_BG = "#0f1724"          # card background
CARD_INSET = "#0b1220"       # inner subtle shading
TEXT_MUTED = "#9aa4b2"
TITLE_COLOR = "#7aa2ff"      # neon-ish title
ACCENT_GRADIENT_START = "#ff5f7a"
ACCENT_GRADIENT_END = "#8b5cf6"
OTHER_COLOR = "#6b7280"
DOT_COLORS = [
    "#ff7a7a","#ffb86b","#ffd36b","#7af58c","#7ad3ff",
    "#a78bfa","#f472b6","#60a5fa","#34d399","#f97316"
]

# Default color mapping for languages (fallback mapping)
DEFAULT_LANGUAGE_COLOR_MAP = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#2b7489",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Shell": "#89e051",
    "PHP": "#4F5D95",
    "Ruby": "#701516",
    "C": "#555555",
    "C++": "#f34b7d",
    "Other": OTHER_COLOR
}

# ---------------- GitHub API helpers ----------------

def get_headers(token: str | None):
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "TechStackVisualizer/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers

def fetch_all_repos(username: str, token: str | None, include_forks: bool=False):
    """Fetch all repos for a user (owner only). Returns list of repo dicts."""
    repos = []
    page = 1
    per_page = 100
    session = requests.Session()
    session.headers.update(get_headers(token))
    while True:
        url = f"{GITHUB_API_BASE}/users/{username}/repos"
        params = {"per_page": per_page, "page": page, "type": "owner", "sort": "updated"}
        r = session.get(url, params=params, timeout=30)
        if r.status_code == 404:
            raise SystemExit(f"User '{username}' not found (HTTP 404).")
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        for repo in data:
            if not include_forks and repo.get("fork"):
                continue
            repos.append(repo)
        if len(data) < per_page:
            break
        page += 1
    return repos

def fetch_langs_for_repo(repo_full_name: str, token: str | None, session: requests.Session) -> dict:
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/languages"
    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.json() or {}

def aggregate_languages(repos: list, token: str | None) -> OrderedDict:
    session = requests.Session()
    session.headers.update(get_headers(token))
    totals = defaultdict(int)
    for repo in repos:
        try:
            langs = fetch_langs_for_repo(repo["full_name"], token, session)
        except Exception as e:
            # warn and skip
            print(f"Warning: languages fetch failed for {repo.get('full_name')}: {e}", file=sys.stderr)
            continue
        for lang, b in langs.items():
            totals[lang] += int(b or 0)
    # sort descending
    ordered = OrderedDict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))
    return ordered

def compute_percentages(lang_bytes: OrderedDict, collapse_threshold=1.0) -> OrderedDict:
    """Return OrderedDict lang -> (bytes, percent_float) and collapse small into Other if needed."""
    total = sum(lang_bytes.values())
    if total == 0:
        return OrderedDict()
    items = []
    other_bytes = 0
    for lang, b in lang_bytes.items():
        pct = (b / total) * 100.0
        if pct < collapse_threshold:
            other_bytes += b
        else:
            items.append((lang, b, pct))
    if other_bytes > 0:
        items.append(("Other", other_bytes, (other_bytes / total) * 100.0))
    items_sorted = sorted(items, key=lambda t: t[1], reverse=True)
    return OrderedDict((lang, (b, round(pct, 2))) for lang, b, pct in items_sorted)

# ---------------- GitHub statistics helpers ----------------

def total_stars(repos: list) -> int:
    return sum(repo.get("stargazers_count", 0) for repo in repos)

def total_commits_for_user_in_repo(repo_full_name: str, username: str, token: str | None, session: requests.Session) -> int:
    """
    Get number of commits authored by username in repo by using commits?author=username&per_page=1
    and parsing Link header for last page. If Link absent, count returned items length.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits"
    params = {"author": username, "per_page": 1}
    r = session.get(url, params=params, timeout=25)
    r.raise_for_status()
    items = r.json()
    if not isinstance(items, list):
        return 0
    if "Link" in r.headers:
        # Link header like: <...page=34>; rel="last", ...
        link = r.headers["Link"]
        # find rel="last"
        for part in link.split(","):
            if 'rel="last"' in part:
                # extract page=NN
                import re
                m = re.search(r'[&?]page=(\d+)', part)
                if m:
                    return int(m.group(1))
        # fallback
    return len(items)

def total_commits_all_repos(repos: list, username: str, token: str | None) -> int:
    session = requests.Session()
    session.headers.update(get_headers(token))
    total = 0
    for repo in repos:
        full_name = repo.get("full_name")
        try:
            c = total_commits_for_user_in_repo(full_name, username, token, session)
            total += c
        except Exception as e:
            # non-fatal
            print(f"Warning: commit count failed for {full_name}: {e}", file=sys.stderr)
    return total

def search_count(query: str, token: str | None) -> int:
    """Use GitHub search API to return the total_count for a query (issues/PRs)."""
    session = requests.Session()
    session.headers.update(get_headers(token))
    url = f"{GITHUB_API_BASE}/search/issues"
    params = {"q": query, "per_page": 1}
    r = session.get(url, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    return int(data.get("total_count", 0))

def prs_and_repos_contributed(username: str, token: str | None):
    """
    Use search API to find PRs authored by username and return:
      - total_prs (int)
      - set of repo full_names where the user has authored PRs (used as contributed repo count)
    """
    session = requests.Session()
    session.headers.update(get_headers(token))
    query = f"type:pr+author:{username}"
    url = f"{GITHUB_API_BASE}/search/issues"
    per_page = 100
    page = 1
    repo_set = set()
    total_prs = 0
    while True:
        params = {"q": query, "per_page": per_page, "page": page}
        r = session.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        if page == 1:
            total_prs = int(data.get("total_count", 0))
        items = data.get("items", [])
        for it in items:
            repo_url = it.get("repository_url")
            if repo_url:
                # repository_url is like https://api.github.com/repos/owner/repo
                repo_full = "/".join(repo_url.split("/")[-2:])
                repo_set.add(repo_full)
        if len(items) < per_page:
            break
        page += 1
    return total_prs, repo_set

def issues_count(username: str, token: str | None) -> int:
    return search_count(f"type:issue+author:{username}", token)

# ---------------- SVG helpers ----------------

def esc(s: str) -> str:
    return html.escape(str(s))

def gradient_def(id_name: str, start: str, end: str) -> str:
    return (
        f'<linearGradient id="{id_name}" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{start}"/>'
        f'<stop offset="100%" stop-color="{end}"/>'
        '</linearGradient>'
    )

def write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ---------------- Card generators (SVG) ----------------

def generate_card_languages_overall(percentages: OrderedDict, out_path: str, username: str):
    """
    Card 1: Single big horizontal bar representing overall distribution (visually like your ref)
    Also lists languages with colored dots and percentages.
    Width fixed to SVG_WIDTH (500).
    """
    width = SVG_WIDTH
    # Layout
    height = 140 + 20  # compact
    bar_y = 54
    bar_height = 14
    legend_y = bar_y + bar_height + 18
    # Build segments for the big horizontal bar
    total_pct = sum(v[1] for v in percentages.values()) or 100.0
    x = CARD_PADDING
    inner_width = width - CARD_PADDING*2
    # Determine color array for languages
    langs = list(percentages.keys())
    colors = []
    for i, lang in enumerate(langs):
        color = DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[i % len(DOT_COLORS)])
        colors.append(color)
    # Construct bar segments as rectangles with gradient overlay
    segs = []
    cur_x = x
    for lang, (b, pct) in percentages.items():
        seg_w = max(1, (pct / 100.0) * inner_width)
        segs.append((cur_x, seg_w, DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[len(segs) % len(DOT_COLORS)])))
        cur_x += seg_w
    # Title and small decorations
    svg = []
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<defs>{gradient_def("g1", ACCENT_GRADIENT_START, ACCENT_GRADIENT_END)}</defs>')
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="{CARD_RADIUS}" fill="{CARD_BG}" />')
    # Title
    svg.append(f'<text x="{CARD_PADDING}" y="{30}" fill="{TITLE_COLOR}" font-size="18" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-weight="700">Most Used Languages</text>')
    # big bar background
    svg.append(f'<rect x="{x}" y="{bar_y}" rx="{bar_height/2}" width="{inner_width}" height="{bar_height}" fill="#0b1220" />')
    # segments
    for sx, sw, col in segs:
        svg.append(f'<rect x="{sx}" y="{bar_y}" width="{sw}" height="{bar_height}" rx="{bar_height/2}" fill="{col}" />')
    # small right rounded cap (ensures trailing rounding)
    # Legend items (dot + label + percent)
    lx = CARD_PADDING
    ly = legend_y
    item_gap_x = 140
    item_gap_y = 22
    idx = 0
    for lang, (b, pct) in percentages.items():
        dot_x = lx + (idx % 2) * item_gap_x
        row_y = ly + (idx//2) * item_gap_y
        color = DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[idx % len(DOT_COLORS)])
        svg.append(f'<circle cx="{dot_x+6}" cy="{row_y}" r="6" fill="{color}" />')
        svg.append(f'<text x="{dot_x+20}" y="{row_y+4}" fill="white" font-size="13" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{esc(lang)}</text>')
        svg.append(f'<text x="{dot_x+110}" y="{row_y+4}" fill="{TEXT_MUTED}" font-size="12" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{pct:.2f}%</text>')
        idx += 1
    # username small
    svg.append(f'<text x="{width - CARD_PADDING}" y="{height-10}" text-anchor="end" fill="{TEXT_MUTED}" font-size="11" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{esc(username)}</text>')
    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))

def generate_card_languages_top5(percentages: OrderedDict, out_path: str, username: str, top_n: int = 5):
    """
    Card 2: Top N languages each with horizontal bar and percent on right.
    Width fixed to SVG_WIDTH.
    """
    width = SVG_WIDTH
    items = list(percentages.items())[:top_n]
    rows = max(3, len(items))
    row_h = 34
    title_h = 50
    height = CARD_PADDING*2 + title_h + row_h*rows
    svg = []
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    svg.append(f'<defs>{gradient_def("g2", ACCENT_GRADIENT_START, ACCENT_GRADIENT_END)}</defs>')
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="{CARD_RADIUS}" fill="{CARD_BG}" />')
    svg.append(f'<text x="{CARD_PADDING}" y="34" fill="{TITLE_COLOR}" font-size="18" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-weight="700">Most Used Languages</text>')
    # rows
    bar_area_x = CARD_PADDING + 110
    bar_area_w = width - bar_area_x - CARD_PADDING - 60
    for i, (lang, (b, pct)) in enumerate(items):
        y = title_h + i*row_h
        # small lang text at left
        svg.append(f'<text x="{CARD_PADDING+8}" y="{y+18}" fill="#7ee6ff" font-size="13" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{esc(lang)}</text>')
        # background bar
        svg.append(f'<rect x="{bar_area_x}" y="{y+6}" rx="8" width="{bar_area_w}" height="12" fill="#0b1220"/>')
        # filled portion (rounded)
        fill_w = max(2, (pct/100.0) * bar_area_w)
        color = DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[i % len(DOT_COLORS)])
        svg.append(f'<rect x="{bar_area_x}" y="{y+6}" rx="8" width="{fill_w}" height="12" fill="{color}" />')
        # percent text at right
        svg.append(f'<text x="{bar_area_x+bar_area_w+12}" y="{y+18}" fill="#bfe6ff" font-size="12" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{pct:.2f}%</text>')
    # username small
    svg.append(f'<text x="{width - CARD_PADDING}" y="{height-10}" text-anchor="end" fill="{TEXT_MUTED}" font-size="11" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{esc(username)}</text>')
    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))

def generate_card_github_stats(stats: dict, out_path: str, username: str):
    """
    Card 3: GitHub stats summary (stars, commits, PRs, Issues, contributed_to)
    Also shows a circular grade ring with text (A+, B, etc). We'll derive a grade from a little heuristic.
    """
    width = SVG_WIDTH
    height = 140 + 30
    svg = []
    svg.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    # gradients
    svg.append('<defs>')
    svg.append(gradient_def("g3", "#f472b6", "#8b5cf6"))
    svg.append('</defs>')
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" rx="{CARD_RADIUS}" fill="{CARD_BG}" />')
    # Title
    svg.append(f'<text x="{CARD_PADDING}" y="{28}" fill="{TITLE_COLOR}" font-size="18" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-weight="700">{esc(username)}\'s GitHub Stats</text>')
    # left-col stats list
    stat_x = CARD_PADDING + 12
    stat_y = 48
    stat_gap = 20
    icon_radius = 8
    # Icons represented by small circles with gradient or colors
    def stat_line(icon_color, label, value, idx):
        y = stat_y + idx*stat_gap
        return (
            f'<circle cx="{stat_x+icon_radius}" cy="{y}" r="{icon_radius}" fill="{icon_color}" />'
            f'<text x="{stat_x +  icon_radius*2 + 8}" y="{y+4}" fill="white" font-size="13" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{esc(label)}</text>'
            f'<text x="{stat_x + 240}" y="{y+4}" fill="{TEXT_MUTED}" font-size="13" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{esc(value)}</text>'
        )
    lines = []
    lines.append(stat_line("#FFD166", "Total Stars Earned:", stats.get("stars", 0), 0))
    lines.append(stat_line("#60A5FA", f"Total Commits:", stats.get("commits", 0), 1))
    lines.append(stat_line("#F97316", f"Total PRs:", stats.get("prs", 0), 2))
    lines.append(stat_line("#FB7185", f"Total Issues:", stats.get("issues", 0), 3))
    # contributed to count (distinct repos from PRs)
    lines.append(stat_line("#C084FC", f"Contributed to:", stats.get("contributed_to", 0), 4))
    svg.extend(lines)
    # right-col: circular grade ring
    ring_cx = width - CARD_PADDING - 70
    ring_cy = 70
    ring_r = 44
    stroke_w = 8
    # compute a score for grade: simple weighted sum scaled to 0..100
    score = 0
    # weights chosen arbitrarily for a visual score
    score += min(stats.get("stars",0), 1000) * 0.02
    score += min(stats.get("commits",0), 2000) * 0.01
    score += min(stats.get("prs",0), 500) * 0.04
    score += min(stats.get("issues",0), 500) * 0.02
    score = max(0, min(100, score))
    # grade mapping
    if score >= 85: grade_text = "A+"
    elif score >= 70: grade_text = "A"
    elif score >= 55: grade_text = "B"
    elif score >= 40: grade_text = "C"
    else: grade_text = "D"
    # ring background
    svg.append(f'<circle cx="{ring_cx}" cy="{ring_cy}" r="{ring_r}" stroke="#0b1220" stroke-width="{stroke_w}" fill="none" />')
    # arc: we use stroke-dasharray to draw progress
    circumference = 2 * math.pi * ring_r
    progress = score / 100.0
    dash = circumference * progress
    gap = circumference - dash
    svg.append(f'<circle cx="{ring_cx}" cy="{ring_cy}" r="{ring_r}" stroke="url(#g3)" stroke-width="{stroke_w}" stroke-linecap="round" fill="none" transform="rotate(-90 {ring_cx} {ring_cy})" stroke-dasharray="{dash} {gap}" />')
    # grade text
    svg.append(f'<text x="{ring_cx}" y="{ring_cy+6}" text-anchor="middle" fill="white" font-size="20" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-weight="700">{grade_text}</text>')
    # small percent label
    svg.append(f'<text x="{ring_cx}" y="{ring_cy+28}" text-anchor="middle" fill="{TEXT_MUTED}" font-size="11" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">{score:.0f}</text>')
    # footer small
    svg.append(f'<text x="{width - CARD_PADDING}" y="{height-10}" text-anchor="end" fill="{TEXT_MUTED}" font-size="11" font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">Generated: {datetime.utcnow().strftime("%Y-%m-%d")}</text>')
    svg.append("</svg>")
    write_file(out_path, "\n".join(svg))

# ---------------- Orchestration and CLI ----------------

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def parse_args():
    p = argparse.ArgumentParser(description="Tech Stack Visualizer - generate 3 gradient/neon-style SVG cards (500px).")
    p.add_argument("--username", "-u", required=True, help="GitHub username to analyze")
    p.add_argument("--token", "-t", default=None, help="GitHub token (or set GITHUB_TOKEN env var)")
    p.add_argument("--output-dir", "-o", default="assets", help="Output folder (default: assets)")
    p.add_argument("--include-forks", action="store_true", help="Include forked repos in language aggregation")
    p.add_argument("--collapse-threshold", type=float, default=1.0, help="Percent threshold below which languages grouped into Other")
    return p.parse_args()

def main():
    args = parse_args()
    username = args.username
    token = args.token or os.environ.get("GITHUB_TOKEN")
    outdir = args.output_dir
    ensure_dir(outdir)

    print(f"[{datetime.utcnow().isoformat()}] Tech Stack Visualizer (Option 2) - user: {username}")

    # 1) Fetch repos
    try:
        repos = fetch_all_repos(username, token, include_forks=args.include_forks)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Failed to fetch repos: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(repos)} repositories.")

    # 2) Aggregate languages
    lang_bytes = aggregate_languages(repos, token)
    percentages = compute_percentages(lang_bytes, collapse_threshold=args.collapse_threshold)
    if not percentages:
        print("No language data to generate charts.", file=sys.stderr)

    # 3) Compute github stats
    stats = {}
    stats["stars"] = total_stars(repos)
    # commits
    print("Computing commits (may take a while for many repos)...")
    stats["commits"] = total_commits_all_repos(repos, username, token)
    # PRs + contributed repos
    print("Fetching PR stats and contributed repos (search API) ...")
    total_prs, repo_set = prs_and_repos_contributed(username, token)
    stats["prs"] = total_prs
    stats["contributed_to"] = len(repo_set)
    # issues
    stats["issues"] = issues_count(username, token)

    # 4) Generate SVGs
    out1 = os.path.join(outdir, "card_languages_overall.svg")
    out2 = os.path.join(outdir, "card_languages_top5.svg")
    out3 = os.path.join(outdir, "card_github_stats.svg")

    print(f"Writing SVGs to {outdir} ...")
    generate_card_languages_overall(percentages, out1, username)
    generate_card_languages_top5(percentages, out2, username, top_n=5)
    generate_card_github_stats(stats, out3, username)

    print("Done. Files created:")
    print(" -", out1)
    print(" -", out2)
    print(" -", out3)

if __name__ == "__main__":
    main()
