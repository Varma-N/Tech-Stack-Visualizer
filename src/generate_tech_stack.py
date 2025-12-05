#!/usr/bin/env python3
"""
generate_tech_stack.py

Tech Stack Visualizer — Neon/Gradient Theme (Option 2)
Generates 3 SVG cards (500px width):

1. card_languages_overall.svg  
2. card_languages_top5.svg  
3. card_github_stats.svg  

Reads:
 - USERNAME from environment or CLI
 - TOKEN from environment or CLI (PAT recommended)

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
        "User-Agent": "TechStackVisualizer/1.0"
    }
    if token:
        h["Authorization"] = f"token {token}"
    return h

# ------------------- API CALLS -------------------

def fetch_all_repos(username, token, include_forks=False):
    repos = []
    page = 1
    session = requests.Session()
    session.headers.update(get_headers(token))

    while True:
        url = f"{GITHUB_API}/users/{username}/repos"
        params = {"per_page": 100, "page": page, "type": "owner", "sort": "updated"}
        r = session.get(url, params=params, timeout=25)
        
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


def fetch_languages(repo_full, token, session):
    url = f"{GITHUB_API}/repos/{repo_full}/languages"
    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.json() or {}


def aggregate_languages(repos, token):
    session = requests.Session()
    session.headers.update(get_headers(token))
    totals = defaultdict(int)

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
    if not total:
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


def search_count(q, token):
    url = f"{GITHUB_API}/search/issues"
    params = {"q": q, "per_page": 1}
    r = requests.get(url, params=params, headers=get_headers(token))
    r.raise_for_status()
    return int(r.json().get("total_count", 0))


def prs_and_contributions(username, token):
    q = f"type:pr+author:{username}"
    url = f"{GITHUB_API}/search/issues"

    session = requests.Session()
    session.headers.update(get_headers(token))

    page = 1
    per_page = 100
    repo_set = set()
    total_prs = 0

    while True:
        params = {"q": q, "page": page, "per_page": per_page}
        r = session.get(url, params=params)
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
    """Efficient commit count (approx using ?author=username & Link header)."""
    session = requests.Session()
    session.headers.update(get_headers(token))

    count = 0
    for repo in repos:
        url = f"{GITHUB_API}/repos/{repo['full_name']}/commits"
        params = {"author": username, "per_page": 1}
        r = session.get(url, params=params)

        if r.status_code not in (200, 201):
            continue

        if "Link" in r.headers:
            link = r.headers["Link"]
            import re
            m = re.search(r'page=(\d+)>; rel="last"', link)
            if m:
                count += int(m.group(1))
            else:
                count += len(r.json())
        else:
            count += len(r.json())

    return count

# ------------------- SVG: CARD 1 -------------------

def card_languages_overall(percentages, out_path, username):
    height = 150

    svg = [f"""
<svg width="{SVG_WIDTH}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<defs>{gradient("grad1", ACCENT_START, ACCENT_END)}</defs>
<rect width="{SVG_WIDTH}" height="{height}" rx="12" fill="{CARD_BG}"/>
<text x="20" y="32" fill="{TITLE_COLOR}" font-size="18" font-weight="700"
      font-family="Segoe UI,Roboto,Helvetica,Arial">Most Used Languages</text>
"""]

    # big bar
    x = 20
    y = 50
    bar_h = 14
    inner_w = SVG_WIDTH - 40

    svg.append(f'<rect x="{x}" y="{y}" width="{inner_w}" height="{bar_h}" rx="8" fill="#0b1220"/>')

    cur_x = x
    langs = list(percentages.keys())

    for i, (lang, (b, pct)) in enumerate(percentages.items()):
        w = max(1, (pct / 100) * inner_w)
        color = DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[i % len(DOT_COLORS)])
        svg.append(f'<rect x="{cur_x}" y="{y}" width="{w}" height="{bar_h}" rx="8" fill="{color}"/>')
        cur_x += w

    # Legend
    lx = 22
    ly = 90
    gap_y = 22

    for i, (lang, (b, pct)) in enumerate(percentages.items()):
        dy = ly + i * gap_y
        color = DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[i % len(DOT_COLORS)])

        svg.append(f'<circle cx="{lx}" cy="{dy}" r="6" fill="{color}"/>')
        svg.append(f'<text x="{lx+18}" y="{dy+5}" fill="white" font-size="13" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(lang)}</text>')
        svg.append(f'<text x="{lx+140}" y="{dy+5}" fill="{TEXT_MUTED}" font-size="12" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{pct:.2f}%</text>')

    # footer username
    svg.append(f'<text x="{SVG_WIDTH-20}" y="{height-10}" fill="{TEXT_MUTED}" text-anchor="end" '
               f'font-size="11" font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(username)}</text>')

    svg.append("</svg>")
    write(out_path, "\n".join(svg))

# ------------------- SVG: CARD 2 -------------------

def card_languages_top5(percentages, out_path, username):
    top = list(percentages.items())[:5]
    rows = len(top)
    height = 160 + rows * 28

    svg = [f"""
<svg width="{SVG_WIDTH}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<rect width="{SVG_WIDTH}" height="{height}" rx="12" fill="{CARD_BG}"/>
<text x="20" y="32" fill="{TITLE_COLOR}" font-size="18" font-weight="700"
      font-family="Segoe UI,Roboto,Helvetica,Arial">Most Used Languages</text>
"""]

    bar_x = 130
    bar_w = SVG_WIDTH - bar_x - 40

    for i, (lang, (b, pct)) in enumerate(top):
        y = 60 + i * 34

        svg.append(f'<text x="28" y="{y+10}" fill="#7ee6ff" font-size="13" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(lang)}</text>')

        svg.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="12" rx="7" fill="#0b1220"/>')

        fill = max(2, (pct / 100) * bar_w)
        color = DEFAULT_LANGUAGE_COLOR_MAP.get(lang, DOT_COLORS[i % len(DOT_COLORS)])
        svg.append(f'<rect x="{bar_x}" y="{y}" width="{fill}" height="12" rx="7" fill="{color}"/>')

        svg.append(f'<text x="{bar_x+bar_w+10}" y="{y+10}" fill="#bfe6ff" font-size="12" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{pct:.2f}%</text>')

    svg.append(f'<text x="{SVG_WIDTH-20}" y="{height-10}" fill="{TEXT_MUTED}" text-anchor="end" '
               f'font-size="11" font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(username)}</text>')

    svg.append("</svg>")
    write(out_path, "\n".join(svg))

# ------------------- SVG: CARD 3 -------------------

def card_github_stats(stats, out_path, username):
    height = 210

    svg = [f"""
<svg width="{SVG_WIDTH}" height="{height}" xmlns="http://www.w3.org/2000/svg">
<defs>{gradient("grad3", ACCENT_START, ACCENT_END)}</defs>
<rect width="{SVG_WIDTH}" height="{height}" rx="12" fill="{CARD_BG}"/>
<text x="20" y="32" fill="{TITLE_COLOR}" font-size="18" font-weight="700"
      font-family="Segoe UI,Roboto,Helvetica,Arial">{esc(username)}'s GitHub Stats</text>
"""]

    # Stats left side
    stats_list = [
        ("#FFD166", "Total Stars:", stats["stars"]),
        ("#60A5FA", "Total Commits:", stats["commits"]),
        ("#F97316", "Total PRs:", stats["prs"]),
        ("#FB7185", "Total Issues:", stats["issues"]),
        ("#C084FC", "Contributed to:", stats["contributed"])
    ]

    y0 = 60
    for i, (color, label, value) in enumerate(stats_list):
        y = y0 + i * 26
        svg.append(f'<circle cx="30" cy="{y-4}" r="7" fill="{color}"/>')
        svg.append(f'<text x="48" y="{y}" fill="white" font-size="13" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{label}</text>')
        svg.append(f'<text x="210" y="{y}" fill="{TEXT_MUTED}" font-size="13" '
                   f'font-family="Segoe UI,Roboto,Helvetica,Arial">{value}</text>')

    # Circle grade (right side)
    cx = SVG_WIDTH - 90
    cy = 90
    r = 42
    stroke_w = 8

    # Compute grade
    score = (
        min(stats["stars"], 300)*0.2 +
        min(stats["commits"], 2000)*0.02 +
        min(stats["prs"], 200)*0.3 +
        min(stats["issues"], 200)*0.15
    )
    score = max(0, min(100, score))

    if score >= 85: grade = "A+"
    elif score >= 70: grade = "A"
    elif score >= 55: grade = "B"
    elif score >= 40: grade = "C"
    else: grade = "D"

    circumference = 2*math.pi*r
    dash = circumference * (score/100)
    gap = circumference - dash

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="#0b1220" '
               f'stroke-width="{stroke_w}" fill="none"/>')

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="url(#grad3)" '
               f'stroke-width="{stroke_w}" fill="none" stroke-linecap="round" '
               f'transform="rotate(-90 {cx} {cy})" '
               f'stroke-dasharray="{dash} {gap}"/>')

    svg.append(f'<text x="{cx}" y="{cy+6}" text-anchor="middle" fill="white" '
               f'font-size="20" font-weight="700" '
               f'font-family="Segoe UI,Roboto,Helvetica,Arial">{grade}</text>')

    svg.append(f'<text x="{cx}" y="{cy+26}" text-anchor="middle" fill="{TEXT_MUTED}" '
               f'font-size="11" font-family="Segoe UI,Roboto,Helvetica,Arial">{int(score)}</text>')

    # Footer
    svg.append(f'<text x="{SVG_WIDTH-20}" y="{height-12}" fill="{TEXT_MUTED}" '
               f'text-anchor="end" font-size="11" font-family="Segoe UI,Roboto,Helvetica,Arial">'
               f'Updated {datetime.utcnow().strftime("%Y-%m-%d")}</text>')

    svg.append("</svg>")

    write(out_path, "\n".join(svg))


# ------------------- MAIN -------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--username", "-u", help="GitHub username")
    p.add_argument("--token", "-t", help="GitHub token")
    return p.parse_args()


def main():
    args = parse_args()

    username = os.environ.get("USERNAME") or args.username
    token = os.environ.get("TOKEN") or args.token

    if not username:
        raise SystemExit("ERROR: USERNAME is required (env USERNAME or --username).")

    print(f"🔧 Generating cards for user: {username}")

    # Fetch repos
    repos = fetch_all_repos(username, token)
    print(f"Fetched {len(repos)} repos")

    # Language stats
    lang_bytes = aggregate_languages(repos, token)
    percentages = compute_percentages(lang_bytes, threshold=1.0)

    # GitHub Stats
    stars = total_stars(repos)
    prs, contributed = prs_and_contributions(username, token)
    commits = total_commits(username, repos, token)
    issues = search_count(f"type:issue+author:{username}", token)

    stats = {
        "stars": stars,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "contributed": contributed,
    }

    # Output files
    outdir = "assets"
    os.makedirs(outdir, exist_ok=True)

    card_languages_overall(percentages, f"{outdir}/card_languages_overall.svg", username)
    card_languages_top5(percentages, f"{outdir}/card_languages_top5.svg", username)
    card_github_stats(stats, f"{outdir}/card_github_stats.svg", username)

    print("🎉 SVG cards generated successfully in /assets")


if __name__ == "__main__":
    main()

