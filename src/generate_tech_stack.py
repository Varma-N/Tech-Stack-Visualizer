#!/usr/bin/env python3
"""
Tech Stack Visualizer — Gradient/Neon Theme (Option 2)
FINAL VERSION WITH FIXES FOR USERNAMES LIKE "Varma-N"

Generates 3 SVG cards:
 - assets/card_languages_overall.svg
 - assets/card_languages_top5.svg
 - assets/card_github_stats.svg

Reads USERNAME and TOKEN from:
 - environment variables (GitHub Actions)
 - or CLI args
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

# ------------------- CONSTANTS -------------------

SVG_WIDTH = 500
CARD_PADDING = 20
CARD_RADIUS = 12

BG_COLOR = "#0b0f17"
CARD_BG = "#0f1724"
TEXT_MUTED = "#9aa4b2"
TITLE_COLOR = "#7aa2ff"

ACCENT_START = "#f472b6"
ACCENT_END   = "#8b5cf6"

DOT_COLORS = [
    "#ff7a7a", "#ffb86b", "#ffd36b", "#7af58c", "#7ad3ff",
    "#a78bfa", "#f472b6", "#60a5fa", "#34d399", "#f97316"
]

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
    "Other": "#6b7280"
}

GITHUB_API = "https://api.github.com"

# ------------------- UTILITY -------------------

def esc(s): return html.escape(str(s))

def gradient(id_name, start, end):
    return f"""
    <linearGradient id="{id_name}" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="{start}"/>
        <stop offset="100%" stop-color="{end}"/>
    </linearGradient>
    """

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def get_headers(token):
    h = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "TechStackVisualizer/Final"
    }
    if token:
        h["Authorization"] = f"token {token}"
    return h

# ------------------- FETCH REPOS -------------------

def fetch_all_repos(username, token, include_forks=False):
    repos = []
    page = 1

    session = requests.Session()
    session.headers.update(get_headers(token))

    while True:
        url = f"{GITHUB_API}/users/{username}/repos"
        params = {"per_page": 100, "page": page, "type": "owner", "sort": "updated"}

        r = session.get(url, params=params)
        
        if r.status_code == 404:
            raise SystemExit(f"User '{username}' not found.")
        
        r.raise_for_status()
        data = r.json()

        if not data:
            break

        for repo in data:
            if not include_forks and repo.get("fork"):
                continue
            repos.append(repo)

        if len(data) < 100:
            break
        page += 1

    return repos

# ------------------- LANGUAGE AGGREGATION -------------------

def fetch_languages(repo_full, token, session):
    url = f"{GITHUB_API}/repos/{repo_full}/languages"
    r = session.get(url)
    r.raise_for_status()
    return r.json() or {}

def aggregate_languages(repos, token):
    totals = defaultdict(int)
    session = requests.Session()
    session.headers.update(get_headers(token))

    for repo in repos:
        try:
            langs = fetch_languages(repo["full_name"], token, session)
        except:
            continue

        for lang, b in langs.items():
            totals[lang] += int(b)

    return OrderedDict(sorted(totals.items(), key=lambda x: x[1], reverse=True))

def compute_percentages(lang_bytes, threshold=1.0):
    total = sum(lang_bytes.values())
    if total == 0:
        return OrderedDict()

    result = []
    other = 0

    for lang, b in lang_bytes.items():
        pct = (b / total) * 100
        if pct < threshold:
            other += b
        else:
            result.append((lang, b, pct))

    if other > 0:
        pct = (other / total) * 100
        result.append(("Other", other, pct))

    result.sort(key=lambda x: x[1], reverse=True)
    return OrderedDict((l, (b, round(p, 2))) for l, b, p in result)

# ------------------- GITHUB STATS -------------------

def total_stars(repos):
    return sum(r.get("stargazers_count", 0) for r in repos)

def safe_search(query, token):
    """Handles search queries safely (with quoted username)."""
    url = f"{GITHUB_API}/search/issues"
    params = {"q": query, "per_page": 1}

    r = requests.get(url, params=params, headers=get_headers(token))
    if r.status_code == 422:
        print("⚠️ Search query failed (422). Returning 0.")
        return 0

    r.raise_for_status()
    return r.json().get("total_count", 0)

def prs_and_contributions(username, token):
    """Quoted username avoids 422 errors."""
    query = f'type:pr author:"{username}"'

    url = f"{GITHUB_API}/search/issues"
    session = requests.Session()
    session.headers.update(get_headers(token))

    page = 1
    per_page = 100
    repo_set = set()
    total_prs = 0

    while True:
        params = {"q": query, "page": page, "per_page": per_page}
        r = session.get(url, params=params)

        if r.status_code == 422:
            print("⚠️ PR Search 422. Returning minimal PR results.")
            return 0, 0

        r.raise_for_status()
        data = r.json()

        if page == 1:
            total_prs = data.get("total_count", 0)

        for item in data.get("items", []):
            repo_url = item.get("repository_url")
            if repo_url:
                repo_set.add("/".join(repo_url.split("/")[-2:]))

        if len(data.get("items", [])) < per_page:
            break

        page += 1

    return total_prs, len(repo_set)

def total_commits(username, repos, token):
    """Approx commit count via ?author=username."""
    session = requests.Session()
    session.headers.update(get_headers(token))

    total = 0

    for repo in repos:
        url = f"{GITHUB_API}/repos/{repo['full_name']}/commits"
        params = {"author": username, "per_page": 1}

        r = session.get(url, params=params)
        if r.status_code != 200:
            continue

        if "Link" in r.headers:
            link = r.headers["Link"]
            import re
            m = re.search(r'page=(\d+)>; rel="last"', link)
            if m:
                total += int(m.group(1))
            else:
                total += len(r.json())
        else:
            total += len(r.json())

    return total

# ------------------- SVG CARD GENERATORS -------------------

### CARD 1 — OVERALL LANGUAGES
def card_languages_overall(percentages, out_path, username):
    # GitHub-like language colors
    GITHUB_COLORS = {
        "Jupyter Notebook": "#DA5B0B",
        "HTML": "#E34C26",
        "Python": "#3572A5",
        "Other": "#6b7280",
    }

    # ---------- CARD DIMENSIONS ----------
    title_y = 32
    bar_y = 52
    bar_h = 14
    side_padding = 20
    inner_w = SVG_WIDTH - (side_padding * 2)

    # ---------- SPLIT LEGEND INTO EVEN COLUMNS ----------
    langs = list(percentages.items())
    total_langs = len(langs)

    if total_langs >= 4:
        mid = (total_langs + 1) // 2
        left_col = langs[:mid]
        right_col = langs[mid:]
    else:
        left_col = langs
        right_col = []

    rows = max(len(left_col), len(right_col))
    row_spacing = 24

    height = 110 + rows * row_spacing

    # ------------------------------------
    # START SVG
    # ------------------------------------
    svg = [f"""
<svg width="{SVG_WIDTH}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<defs>{gradient("g1", ACCENT_START, ACCENT_END)}</defs>

<rect width="{SVG_WIDTH}" height="{height}" rx="12" fill="{CARD_BG}"/>

<text x="{side_padding}" y="{title_y}" fill="{TITLE_COLOR}" font-size="18"
      font-weight="700" font-family="Segoe UI,Roboto,Helvetica,Arial">
    Overall Language Breakdown
</text>
"""]

    # ----------- MAIN SEGMENTED BAR -----------
    svg.append(
        f'<rect x="{side_padding}" y="{bar_y}" width="{inner_w}" height="{bar_h}" '
        f'rx="8" fill="#0b1220"/>'
    )

    cur_x = side_padding

    segments = []  # store (lang, color)

    for i, (lang, (b, pct)) in enumerate(langs):
        w = max(2, (pct / 100) * inner_w)
        color = GITHUB_COLORS.get(lang, DOT_COLORS[i % len(DOT_COLORS)])
        segments.append((lang, color))

        svg.append(f'<rect x="{cur_x}" y="{bar_y}" width="{w}" height="{bar_h}" '
                   f'rx="8" fill="{color}"/>')
        cur_x += w

    # ----------- BUBBLE STACK (GitHub-style) -----------
    bubble_r = 4          # smaller → professional look
    bubble_spacing = 22   # wider → no overlap

    total_bubbles_w = len(segments) * bubble_spacing
    bubble_start = side_padding + inner_w - total_bubbles_w + bubble_r

    for i, (_, color) in enumerate(segments):
        cx = bubble_start + (i * bubble_spacing)
        cy = bar_y + bar_h / 2
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="{bubble_r}" fill="{color}"/>')

    # ----------- LEGEND (Even 2-column layout) -----------
    legend_start_y = bar_y + 45
    col_x1 = side_padding
    col_x2 = SVG_WIDTH // 2 + 10

    for row in range(rows):
        y = legend_start_y + row * row_spacing

        # Left column
        if row < len(left_col):
            lang, (b, pct) = left_col[row]
            color = GITHUB_COLORS.get(lang, "#ccc")

            svg.append(f'<circle cx="{col_x1}" cy="{y}" r="6" fill="{color}"/>')
            svg.append(
                f'<text x="{col_x1+18}" y="{y+4}" fill="white" font-size="13" '
                f'font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(lang)}</text>'
            )
            svg.append(
                f'<text x="{col_x1+140}" y="{y+4}" fill="{TEXT_MUTED}" font-size="12" '
                f'font-family="Segoe UI,Roboto,Helvetica,Arial">{pct:.2f}%</text>'
            )

        # Right column
        if row < len(right_col):
            lang, (b, pct) = right_col[row]
            color = GITHUB_COLORS.get(lang, "#ccc")

            svg.append(f'<circle cx="{col_x2}" cy="{y}" r="6" fill="{color}"/>')
            svg.append(
                f'<text x="{col_x2+18}" y="{y+4}" fill="white" font-size="13" '
                f'font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(lang)}</text>'
            )
            svg.append(
                f'<text x="{col_x2+140}" y="{y+4}" fill="{TEXT_MUTED}" font-size="12" '
                f'font-family="Segoe UI,Roboto,Helvetica,Arial">{pct:.2f}%</text>'
            )

    svg.append("</svg>")
    write(out_path, "\n".join(svg))

    

### CARD 2 — TOP 5 LANGUAGES
def card_languages_top5(percentages, out_path, username):
    # GitHub accurate colors
    GITHUB_COLORS = {
        "Jupyter Notebook": "#DA5B0B",
        "HTML": "#E34C26",
        "Python": "#3572A5",
        "Other": "#6b7280",
    }

    # extract top 5 languages only
    top = list(percentages.items())[:5]

    # layout constants (matching GitHub styling)
    TITLE_Y = 32
    ROW_GAP = 32
    CARD_PADDING = 20
    BAR_HEIGHT = 12

    width = SVG_WIDTH
    height = 110 + len(top) * ROW_GAP

    # bar layout
    label_x = CARD_PADDING + 30
    bar_x = 160         # bar start shifted right for long names
    bar_w = width - bar_x - 70  # leave room for % text

    svg = [f"""
<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<rect width="{width}" height="{height}" rx="12" fill="{CARD_BG}"/>

<!-- Title -->
<text x="{CARD_PADDING}" y="{TITLE_Y}" fill="{TITLE_COLOR}" 
      font-size="18" font-weight="700"
      font-family="Segoe UI,Roboto,Helvetica,Arial">
    Top 5 Languages
</text>
"""]

    # =========================
    # ROWS (Label + Dot + Bar)
    # =========================

    for i, (lang, (b, pct)) in enumerate(top):
        y = 60 + i * ROW_GAP

        # GitHub color priority
        color = GITHUB_COLORS.get(
            lang,
            DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[i % len(DOT_COLORS)])
        )

        # Dot icon
        svg.append(
            f'<circle cx="{CARD_PADDING + 6}" cy="{y+4}" r="5" fill="{color}" />'
        )

        # Language name
        svg.append(
            f'<text x="{label_x}" y="{y+8}" fill="white" font-size="13" '
            f'font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(lang)}</text>'
        )

        # Background bar
        svg.append(
            f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="{BAR_HEIGHT}" '
            f'rx="7" fill="#0b1220"/>'
        )

        # Progress fill
        fill_w = max(2, (pct / 100) * bar_w)
        svg.append(
            f'<rect x="{bar_x}" y="{y}" width="{fill_w}" height="{BAR_HEIGHT}" '
            f'rx="7" fill="{color}"/>'
        )

        # Percentage text
        svg.append(
            f'<text x="{bar_x + bar_w + 15}" y="{y+10}" fill="#bfe6ff" font-size="12" '
            f'font-family="Segoe UI,Roboto,Helvetica,Arial">{pct:.2f}%</text>'
        )

    svg.append("</svg>")
    write(out_path, "\n".join(svg))

### CARD 3 — GITHUB STATS
def card_github_stats(stats, out_path, username):
    height = 210

    svg = [f"""
<svg width="{SVG_WIDTH}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<defs>{gradient("g3", ACCENT_START, ACCENT_END)}</defs>
<rect width="{SVG_WIDTH}" height="{height}" rx="12" fill="{CARD_BG}"/>
<text x="20" y="32" fill="{TITLE_COLOR}" font-size="18" font-weight="700"
      font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(username)}'s GitHub Stats</text>
"""]

    # Left stats list
    stats_items = [
        ("#FFD166", "Total Stars:", stats["stars"]),
        ("#60A5FA", "Total Commits:", stats["commits"]),
        ("#F97316", "Total PRs:", stats["prs"]),
        ("#FB7185", "Total Issues:", stats["issues"]),
        ("#C084FC", "Contributed to:", stats["contributed"]),
    ]

    y0 = 60
    for i, (color, text, value) in enumerate(stats_items):
        y = y0 + i * 28
        svg.append(f'<circle cx="30" cy="{y-4}" r="7" fill="{color}"/>')
        svg.append(f'<text x="50" y="{y}" fill="white" font-size="13" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{text}</text>')
        svg.append(f'<text x="220" y="{y}" fill="{TEXT_MUTED}" font-size="13" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{value}</text>')

    # Circle grade on right
    cx = SVG_WIDTH - 90
    cy = 90
    r = 42
    stroke = 8

    score = (
        min(stats["stars"], 300) * 0.2 +
        min(stats["commits"], 2000) * 0.02 +
        min(stats["prs"], 200) * 0.3 +
        min(stats["issues"], 200) * 0.15
    )
    score = max(0, min(100, score))

    if score >= 85: grade = "A+"
    elif score >= 70: grade = "A"
    elif score >= 55: grade = "B"
    elif score >= 40: grade = "C"
    else: grade = "D"

    circumference = 2 * math.pi * r
    dash = circumference * (score / 100)
    gap = circumference - dash

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="#0b1220" stroke-width="{stroke}" fill="none"/>')

    svg.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="url(#g3)" stroke-width="{stroke}" '
        f'stroke-linecap="round" fill="none" transform="rotate(-90 {cx} {cy})" '
        f'stroke-dasharray="{dash} {gap}"/>'
    )

    svg.append(f'<text x="{cx}" y="{cy+6}" text-anchor="middle" fill="white" '
               f'font-size="20" font-weight="700" '
               f'font-family="Segoe UI,Roboto,Helvetica,Arial">{grade}</text>')

    svg.append(f'<text x="{cx}" y="{cy+26}" text-anchor="middle" fill="{TEXT_MUTED}" '
               f'font-size="11" font-family="Segoe UI,Roboto,Helvetica,Arial">{int(score)}</text>')

    svg.append("</svg>")
    write(out_path, "\n".join(svg))

# ------------------- MAIN -------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--username")
    p.add_argument("--token")
    return p.parse_args()

def main():
    args = parse_args()

    username = os.environ.get("USERNAME") or args.username
    token = os.environ.get("TOKEN") or args.token

    if not username:
        raise SystemExit("ERROR: USERNAME not provided.")

    print(f"🚀 Generating tech stack cards for: {username}")

    repos = fetch_all_repos(username, token)
    print(f"✔ Fetched {len(repos)} repositories")

    # Compute languages
    lang_bytes = aggregate_languages(repos, token)
    percentages = compute_percentages(lang_bytes, threshold=1.0)

    # Compute stats
    stars = total_stars(repos)
    prs, contributed = prs_and_contributions(username, token)
    commits = total_commits(username, repos, token)
    issues = safe_search(f'type:issue author:"{username}"', token)

    stats = {
        "stars": stars,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "contributed": contributed
    }

    out = "assets"
    os.makedirs(out, exist_ok=True)

    card_languages_overall(percentages, f"{out}/card_languages_overall.svg", username)
    card_languages_top5(percentages, f"{out}/card_languages_top5.svg", username)
    card_github_stats(stats, f"{out}/card_github_stats.svg", username)

    print("🎉 Done! All cards generated successfully.")

if __name__ == "__main__":
    main()
