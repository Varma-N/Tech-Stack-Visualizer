#!/usr/bin/env python3
"""
generate_tech_stack.py

Fetch GitHub repositories for a user, aggregate language statistics,
produce two visualizations (vertical donut chart + tech stack card),
and export them to assets/ as PNG or SVG.

Usage (CLI):
    python src/generate_tech_stack.py --username NANDI_MADAN_GOPAL_VARMA
    or set USERNAME / TOKEN env vars
"""

from __future__ import annotations
import os
import sys
import argparse
import json
import math
import textwrap
from typing import Dict, List, Tuple
import requests
import matplotlib.pyplot as plt
import numpy as np

# ---------- Configuration defaults ----------
DEFAULT_OUTPUT_DIR = "assets"
DEFAULT_IMAGE_FORMAT = "png"  # png or svg
DEFAULT_THEME = "light"  # or "dark"
DEFAULT_OTHER_THRESHOLD_PCT = 1.0  # languages <= this percent will be grouped into "Other"
GITHUB_API = "https://api.github.com"

# ---------- Helpers: HTTP & GitHub ----------
def github_get(url: str, token: str | None = None, params=None):
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 401:
        raise SystemExit("Unauthorized: check your TOKEN.")
    resp.raise_for_status()
    return resp.json()

def fetch_all_repos(username: str, token: str | None, include_private: bool = False) -> List[Dict]:
    """Fetch public repos for username. If token and include_private True, fetch private as well."""
    repos = []
    page = 1
    per_page = 100
    while True:
        params = {"per_page": per_page, "page": page, "type": "owner"}
        url = f"{GITHUB_API}/users/{username}/repos"
        data = github_get(url, token, params=params)
        if not isinstance(data, list):
            raise SystemExit(f"Unexpected response fetching repos: {data}")
        repos.extend(data)
        if len(data) < per_page:
            break
        page += 1
    # If token and include_private and the user is the authenticated user, their private repos can be fetched via /user/repos
    if token and include_private:
        # Fetch authenticated user's repos (may include private) and filter by owner login
        page = 1
        more = []
        while True:
            params = {"per_page": per_page, "page": page}
            data = github_get(f"{GITHUB_API}/user/repos", token, params=params)
            if not isinstance(data, list):
                break
            more.extend(data)
            if len(data) < per_page:
                break
            page += 1
        # filter repos owned by username and not already present (avoid duplication)
        existing_names = {r["name"] for r in repos}
        for r in more:
            if r.get("owner", {}).get("login") == username and r["name"] not in existing_names:
                repos.append(r)
    return repos

def fetch_repo_languages(owner: str, repo: str, token: str | None) -> Dict[str, int]:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/languages"
    return github_get(url, token)

# ---------- Aggregation ----------
def aggregate_languages(repos: List[Dict], token: str | None) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for r in repos:
        try:
            langs = fetch_repo_languages(r["owner"]["login"], r["name"], token)
        except requests.HTTPError as e:
            print(f"Warning: failed to fetch languages for {r['name']}: {e}", file=sys.stderr)
            continue
        for lang, bytes_count in langs.items():
            totals[lang] = totals.get(lang, 0) + bytes_count
    return totals

def compute_percentages(totals: Dict[str, int]) -> List[Tuple[str, float, int]]:
    """Return list of (language, pct, bytes) sorted descending by bytes."""
    total_bytes = sum(totals.values())
    if total_bytes == 0:
        return []
    items = [(lang, (bytes_count / total_bytes) * 100.0, bytes_count) for lang, bytes_count in totals.items()]
    items.sort(key=lambda x: x[2], reverse=True)
    return items

# ---------- Visualization utilities ----------
def get_colors(n: int, theme: str = "light"):
    cmap = plt.get_cmap("tab20")
    # sample the colormap evenly
    colors = [cmap(i % 20) for i in range(n)]
    if theme == "dark":
        # slightly increase alpha for dark theme
        colors = [(r, g, b, 0.95) for (r, g, b, a) in colors]
    return colors

def prepare_data_for_plot(items: List[Tuple[str, float, int]], other_threshold_pct: float):
    """Group small languages into 'Other' if below threshold percent."""
    if not items:
        return items
    main = []
    other_sum = 0
    for lang, pct, bytes_ in items:
        if pct <= other_threshold_pct:
            other_sum += bytes_
        else:
            main.append((lang, pct, bytes_))
    if other_sum > 0:
        # recompute percentage for other (based on bytes)
        all_bytes = sum(bytes_ for _, _, bytes_ in items)
        other_pct = (other_sum / all_bytes) * 100.0
        main.append(("Other", other_pct, other_sum))
        main.sort(key=lambda x: x[2], reverse=True)
    return main

def draw_vertical_donut(items: List[Tuple[str, float, int]],
                        out_path: str,
                        fmt: str = "png",
                        theme: str = "light",
                        title: str | None = None):
    """
    Vertical donut chart:
    - A tall canvas with a donut near the top and labelled stacked legend below.
    """
    if not items:
        # create a minimal placeholder
        fig, ax = plt.subplots(figsize=(6, 8))
        ax.text(0.5, 0.5, "No language data", ha="center", va="center", fontsize=18)
        ax.axis("off")
        fig.savefig(out_path, bbox_inches="tight", dpi=150, format=fmt)
        plt.close(fig)
        return

    labels = [f"{lang} ({pct:.1f}%)" for lang, pct, _ in items]
    sizes = [pct for _, pct, _ in items]
    colors = get_colors(len(items), theme)

    # Tall figure
    fig = plt.figure(figsize=(6, 10), dpi=150)
    if theme == "dark":
        fig.patch.set_facecolor("#0f1720")
    # donut axes
    donut_ax = fig.add_axes([0.15, 0.55, 0.7, 0.35])  # x, y, width, height
    donut_ax.pie(sizes,
                 labels=None,
                 startangle=90,
                 counterclock=False,
                 wedgeprops=dict(width=0.35, edgecolor='w'),
                 colors=colors)
    donut_ax.axis("equal")
    if title:
        donut_ax.set_title(title, fontsize=16, pad=12)

    # Legend / stacked list below — large, readable
    legend_ax = fig.add_axes([0.08, 0.06, 0.84, 0.42])
    legend_ax.axis("off")

    # draw colored squares + text entries vertically
    y = 0.95
    step = 0.12 if len(items) <= 8 else 0.09
    for i, (lang, pct, bytes_) in enumerate(items):
        rect = plt.Rectangle((0.05, y - 0.05), 0.08, 0.08, facecolor=colors[i], transform=legend_ax.transAxes)
        legend_ax.add_patch(rect)
        legend_ax.text(0.16, y, f"{lang}", transform=legend_ax.transAxes, fontsize=12, va="center")
        legend_ax.text(0.85, y, f"{pct:.1f}%", transform=legend_ax.transAxes, fontsize=12, va="center", ha="right")
        y -= step
        if y < 0.05:
            break

    fig.savefig(out_path, bbox_inches="tight", dpi=150, format=fmt)
    plt.close(fig)

def draw_tech_stack_card(items: List[Tuple[str, float, int]],
                         out_path: str,
                         fmt: str = "png",
                         theme: str = "light",
                         username: str | None = None):
    """
    A rectangular card showing language names and percentages in a modern style.
    """
    width = 1200
    height = 400
    dpi = 150
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    if theme == "dark":
        fig.patch.set_facecolor("#0d1117")
        text_color = "#e6eef6"
    else:
        fig.patch.set_facecolor("#ffffff")
        text_color = "#111827"

    # Title
    title_text = f"{username or 'Tech Stack'} — Language distribution"
    ax.text(0.05, 0.78, title_text, fontsize=22, fontweight="600", color=text_color)

    # small subtitle
    ax.text(0.05, 0.72, "Generated by Tech Stack Visualizer", fontsize=10, color=text_color)

    # compute layout for language blocks
    max_cols = 6
    n = len(items)
    colors = get_colors(n, theme)
    box_w = 0.14
    box_h = 0.22
    x0 = 0.05
    y0 = 0.38
    gap_x = 0.02
    gap_y = 0.04

    for i, (lang, pct, bytes_) in enumerate(items):
        col = i % max_cols
        row = i // max_cols
        x = x0 + col * (box_w + gap_x)
        y = y0 - row * (box_h + gap_y)
        # color swatch
        sw_rect = plt.Rectangle((x, y - 0.03), 0.05, 0.06, facecolor=colors[i])
        ax.add_patch(sw_rect)
        # language name + pct
        ax.text(x + 0.06, y, f"{lang}", fontsize=14, fontweight="600", color=text_color, va="top")
        ax.text(x + 0.06, y - 0.09, f"{pct:.1f}%", fontsize=13, color="#6b7280" if theme == "light" else "#9aa6b2")
    # footer small note
    ax.text(0.05, 0.02, "Data aggregated from GitHub repositories", fontsize=9, color=text_color)

    fig.savefig(out_path, bbox_inches="tight", dpi=dpi, format=fmt)
    plt.close(fig)

# ---------- Persist outputs ----------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

# ---------- Commit helper (for GitHub Actions) ----------
def commit_and_push_assets(asset_paths: List[str], commit_message: str = "chore: update tech stack assets"):
    """
    If running inside GitHub Actions or a repo with git available, stage, commit, and push assets.
    This function assumes git is already configured in the environment (or in Actions).
    """
    import subprocess
    try:
        subprocess.run(["git", "add"] + asset_paths, check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push"], check=True)
    except Exception as e:
        print("Warning: failed to commit/push assets automatically:", e)

# ---------- CLI + main ----------
def load_config_file(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_args():
    parser = argparse.ArgumentParser(
        prog="generate_tech_stack.py",
        description="Generate tech stack visualizations from GitHub language stats."
    )
    parser.add_argument("--username", "-u", help="GitHub username (overrides config/env)")
    parser.add_argument("--token", "-t", help="GitHub token (optional)", default=None)
    parser.add_argument("--config", "-c", help="Path to JSON config (default: config_example.json)", default="config_example.json")
    parser.add_argument("--output", "-o", help="Output directory for assets", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--format", "-f", choices=["png", "svg"], default=DEFAULT_IMAGE_FORMAT)
    parser.add_argument("--theme", choices=["light", "dark"], default=DEFAULT_THEME)
    parser.add_argument("--include-private", action="store_true", help="Attempt to include private repos (requires token)")
    parser.add_argument("--no-commit", action="store_true", help="Don't attempt to git commit/push the assets (useful for local)")
    parser.add_argument("--other-threshold", type=float, default=DEFAULT_OTHER_THRESHOLD_PCT, help="group languages <= this percent into 'Other'")
    return parser.parse_args()

def main():
    args = parse_args()

    # load config file
    config = load_config_file(args.config)
    # precedence: CLI -> env -> config file -> exit if username missing
    username = args.username or os.environ.get("USERNAME") or config.get("username")
    token = args.token or os.environ.get("TOKEN") or config.get("token")
    include_private = args.include_private or config.get("include_private", False)

    if not username:
        print("Error: GitHub username must be provided via --username, USERNAME env, or config file.")
        sys.exit(1)

    print(f"Fetching repos for user: {username} ...")
    repos = fetch_all_repos(username, token, include_private=include_private)
    print(f"Found {len(repos)} repos (owned).")

    totals = aggregate_languages(repos, token)
    items = compute_percentages(totals)
    items = prepare_data_for_plot(items, other_threshold_pct=args.other_threshold)

    ensure_dir(args.output)

    # Filenames
    donut_file = os.path.join(args.output, f"{username}_vertical_donut.{args.format}")
    card_file = os.path.join(args.output, f"{username}_tech_stack_card.{args.format}")

    print("Generating vertical donut:", donut_file)
    draw_vertical_donut(items, donut_file, fmt=args.format, theme=args.theme, title=f"{username}'s Languages")

    print("Generating tech stack card:", card_file)
    draw_tech_stack_card(items, card_file, fmt=args.format, theme=args.theme, username=username)

    print("Wrote assets:", donut_file, card_file)

    if not args.no_commit:
        # If inside GitHub Actions, GITHUB_ACTIONS env var exists; otherwise attempt to commit locally
        asset_paths = [donut_file, card_file]
        try:
            commit_and_push_assets(asset_paths)
            print("Committed & pushed assets (if git available and configured).")
        except Exception as e:
            print("Skipping commit step:", e)

if __name__ == "__main__":
    main()
