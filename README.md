# 🚀 Tech Stack Visualizer

**Tech Stack Visualizer** is a fully automated, GitHub-native project that analyzes a developer’s GitHub repositories and generates **clean, modern SVG cards** representing their **overall programming language usage** and **GitHub activity statistics**.  
These visuals are designed to be embedded directly into GitHub READMEs, portfolios, and developer profiles.

The project is **forkable**, **customizable**, and **runs automatically** using GitHub Actions.

---

## ✨ Features

### 🔍 Repository & Language Analysis
- Fetches **all GitHub repositories** of a user
- Aggregates **language usage across repositories**
- Calculates **percentage contribution per language**
- Groups minor languages into **“Other”** for clarity

### 🎨 Visual SVG Cards
- **Overall Language Breakdown**
  - Segmented horizontal bar
  - Accurate percentage legend
  - GitHub-style spacing and colors
- **GitHub Stats Card**
  - Total commits
  - Pull requests
  - Issues
  - Stars
  - Repositories contributed to
- SVG assets optimized for **GitHub README rendering**

### 🤖 Full Automation
- Runs automatically via **GitHub Actions**
- Supports **daily scheduled runs** and **manual triggers**
- Regenerates SVG assets and commits them automatically

### 🔁 Forkable & Customizable
- Easy username configuration
- Optional GitHub token support:
  - Higher API rate limits
  - Access to private repositories
- Clean, minimal project structure
- Uses only free and open-source tools

---

## 🧠 How It Works

1. Fetches repository and language data from GitHub APIs  
2. Aggregates language usage across all repositories  
3. Computes normalized language percentages  
4. Programmatically renders SVG cards  
5. Saves generated assets to the `assets/` directory  
6. GitHub Actions commits updated assets automatically  

---

## 🗂️ Project Structure

```
Tech-Stack-Visualizer/
├── assets/
│ ├── overall_languages.svg
│ └── github_stats.svg
│
├── src/
│ └── generate_tech_stack.py
│
├── .github/
│ └── workflows/
│ └── generate-assets.yml
│
├── requirements.txt
├── LICENSE
└── README.md
```

---

## ⚙️ Setup & Usage

### 1️⃣ Fork the Repository
Fork this repository to your own GitHub account.

---

### 2️⃣ Configure GitHub Actions Secrets

Go to:

**Settings → Secrets and variables → Actions**

Add the following secrets:

| Name | Description |
|-----|------------|
| `USERNAME` | Your GitHub username |
| `TOKEN` | *(Optional)* GitHub Personal Access Token |

> The token is recommended for higher rate limits and private repository access.

---

### 3️⃣ Run the Workflow

- The workflow runs **daily** automatically
- Can also be triggered manually from the **Actions** tab
- Updated SVG assets are committed to the repository

No local setup is required.

---

### 4️⃣ Embed in Your README

Once generated, use the SVGs in your README:

```md
![Overall Language Breakdown](./assets/overall_languages.svg)
![GitHub Stats](./assets/github_stats.svg)
```
---

### 🧰 Tech Stack

Python – Data fetching, aggregation, SVG generation

GitHub REST & GraphQL APIs – Repository and contribution data

SVG – Lightweight, scalable visuals

GitHub Actions – Automation and scheduling

Git – Version-controlled asset updates

---

### 🛡️ License

This project is licensed under the MIT License - free to use, modify, and distribute.
