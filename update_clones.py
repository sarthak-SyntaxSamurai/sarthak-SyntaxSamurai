#!/usr/bin/env python3
"""
SyntaxSamurai GitHub Clone Counter & History Tracker
Automatically discovers all own repositories (excluding forks),
fetches 14-day rolling clone statistics from GitHub Traffic API,
aggregates permanent historical clone counts in clones_history.json,
and updates the Total_Clones badge in README.md.

Works both in GitHub Actions CI/CD and locally on macOS.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

# Dynamically resolve repository root directory
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(REPO_DIR, "clones_history.json")
README_FILE = os.path.join(REPO_DIR, "README.md")
GITHUB_USER = "sarthak-SyntaxSamurai"

def get_sanitized_env():
    """Returns environment with standard PATH and removes invalid GITHUB_TOKEN if running locally."""
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")
    return env

def run_cmd(cmd, cwd=REPO_DIR, clean_env=True):
    """Executes a shell command safely."""
    env = get_sanitized_env()
    # In local environment, if GITHUB_TOKEN is broken, remove it so gh uses Keychain
    if clean_env and not os.environ.get("CI"):
        env.pop("GITHUB_TOKEN", None)
        env.pop("GH_TOKEN", None)
    
    result = subprocess.run(cmd, shell=True, env=env, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, result.stderr.strip()
    return result.stdout.strip(), None

def get_own_repositories():
    """Discovers all non-fork repositories owned by the user."""
    # 1. Try gh CLI
    cmd = f"gh repo list {GITHUB_USER} --limit 100 --json nameWithOwner,isFork"
    out, err = run_cmd(cmd, clean_env=True)
    if out:
        try:
            repos_json = json.loads(out)
            own_repos = [r["nameWithOwner"] for r in repos_json if not r.get("isFork", False)]
            if own_repos:
                return own_repos
        except Exception:
            pass

    # 2. Fallback to hardcoded list of own repositories if dynamic fetch fails
    return [
        f"{GITHUB_USER}/FrogDrop",
        f"{GITHUB_USER}/sarthak-SyntaxSamurai",
        f"{GITHUB_USER}/homebrew-tap",
        f"{GITHUB_USER}/popblock",
        f"{GITHUB_USER}/New",
        f"{GITHUB_USER}/grind-4year-ece-roadmap",
        f"{GITHUB_USER}/desktop-tutorial"
    ]

def fetch_traffic_clones(repo_slug):
    """Fetches clone traffic via urllib (if token provided) or fallback to GitHub CLI."""
    token = os.environ.get("TRAFFIC_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    
    # 1. Try direct HTTP with token
    if token:
        url = f"https://api.github.com/repos/{repo_slug}/traffic/clones"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "SyntaxSamurai-Clone-Tracker",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28"
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data
        except Exception:
            pass

    # 2. Fallback to GitHub CLI (gh api) with sanitized environment
    cmd = f"gh api repos/{repo_slug}/traffic/clones"
    output, err = run_cmd(cmd, clean_env=True)
    if output:
        try:
            data = json.loads(output)
            return data
        except Exception as e:
            print(f"[{repo_slug}] Failed to parse JSON from GitHub CLI output: {e}")
    else:
        # Ignore 404/permissions errors gracefully on empty/unsupported repos
        if err and "404" not in err:
            print(f"[{repo_slug}] Traffic query note: {err}")

    return None

def main():
    print("=" * 65)
    print("🚀 SyntaxSamurai Total Clones Sync (Own Repos Only - No Forks)")
    print("=" * 65)

    # 1. Load and migrate existing history
    raw_history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                raw_history = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load existing history ({e}), starting fresh.")
            raw_history = {}

    # Migrate from flat dates format to per-repo structure if needed
    history = {}
    if any(k.startswith("202") for k in raw_history.keys()):
        print("📦 Migrating existing FrogDrop flat history into structured per-repo store...")
        history[f"{GITHUB_USER}/FrogDrop"] = raw_history
    else:
        history = raw_history

    initial_history_json = json.dumps(history, sort_keys=True)
    total_new_entries = 0

    # 2. Discover all non-fork repositories
    own_repos = get_own_repositories()
    print(f"📋 Discovered {len(own_repos)} own original repositories (Forks excluded):")
    for r in own_repos:
        print(f"  • {r}")
    print("-" * 65)

    # 3. Fetch traffic data for each own repo
    for repo_slug in own_repos:
        if repo_slug not in history:
            history[repo_slug] = {}

        traffic_data = fetch_traffic_clones(repo_slug)
        if not traffic_data:
            continue

        clones = traffic_data.get("clones", [])
        for entry in clones:
            timestamp = entry.get("timestamp")
            count = entry.get("count", 0)
            if not timestamp:
                continue

            # Update count if new or higher than previous record
            if timestamp not in history[repo_slug] or count > history[repo_slug][timestamp]:
                history[repo_slug][timestamp] = count
                total_new_entries += 1

    # 4. Save updated history
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, sort_keys=True)

    # 5. Calculate per-repo and grand total clones
    print("\n📊 Current Clones Breakdown:")
    grand_total = 0
    for repo_slug, days in sorted(history.items()):
        repo_sum = sum(days.values())
        grand_total += repo_sum
        print(f"  • {repo_slug:<40}: {repo_sum:>4} clones ({len(days)} recorded dates)")

    print("=" * 65)
    print(f"🔥 Grand Total Clones (Own Repos): {grand_total} (+{total_new_entries} updates)")
    print("=" * 65)

    # 6. Update README.md badge
    if not os.path.exists(README_FILE):
        print(f"Error: README.md not found at {README_FILE}")
        sys.exit(1)

    with open(README_FILE, "r", encoding="utf-8") as f:
        readme_content = f.read()

    # Match badge format: Total_Clones-<number>-00FF66 or Total_Clones-<number>%2B-00FF66
    pattern = r"Total_Clones-[^-\?]+-00FF66"
    replacement = f"Total_Clones-{grand_total}-00FF66"

    new_readme, num_subs = re.subn(pattern, replacement, readme_content)
def generate_stats_svg(grand_total, repo_count):
    """Generates a 100% reliable, zero-downtime, static vector SVG stats card."""
    os.makedirs(os.path.join(REPO_DIR, "assets"), exist_ok=True)
    svg_path = os.path.join(REPO_DIR, "assets", "github_stats.svg")
    svg_content = f"""<svg width="800" height="250" viewBox="0 0 800 250" fill="none" xmlns="http://www.w3.org/2000/svg">
  <style>
    .header {{ font: 600 17px -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #F0F6FC; }}
    .sub {{ font: 400 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #8B949E; }}
    .metric-val {{ font: 700 22px -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #00FF66; }}
    .metric-lbl {{ font: 500 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #C9D1D9; }}
    .lang-lbl {{ font: 500 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #8B949E; }}
  </style>

  <!-- Background Canvas -->
  <rect width="800" height="250" rx="16" fill="#0D1117" stroke="#30363D" stroke-width="1.5"/>

  <!-- Top Ambient Glow -->
  <circle cx="400" cy="0" r="180" fill="#00FF66" fill-opacity="0.06"/>

  <!-- Header -->
  <circle cx="28" cy="32" r="6" fill="#00FF66"/>
  <text x="44" y="37" class="header">Sarthak Anand (@sarthak-SyntaxSamurai) • 2026 Developer Analytics</text>
  <text x="760" y="36" text-anchor="end" class="sub">Verified GitHub Stats</text>
  <line x1="20" y1="55" x2="780" y2="55" stroke="#21262D" stroke-width="1"/>

  <!-- 4 Stat Metric Cards -->
  <!-- Card 1: Total Clones -->
  <rect x="24" y="70" width="176" height="85" rx="10" fill="#161B22" stroke="#30363D" stroke-width="1"/>
  <text x="40" y="98" class="metric-lbl">🔥 Total Clones</text>
  <text x="40" y="132" class="metric-val">{grand_total}+</text>

  <!-- Card 2: Own Repositories -->
  <rect x="214" y="70" width="176" height="85" rx="10" fill="#161B22" stroke="#30363D" stroke-width="1"/>
  <text x="230" y="98" class="metric-lbl">📦 Public Repos</text>
  <text x="230" y="132" class="metric-val">{repo_count} Projects</text>

  <!-- Card 3: Flagship App -->
  <rect x="404" y="70" width="186" height="85" rx="10" fill="#161B22" stroke="#30363D" stroke-width="1"/>
  <text x="420" y="98" class="metric-lbl">🐸 Flagship Companion</text>
  <text x="420" y="132" class="metric-val" style="fill: #38BDF8;">FrogDrop v2.2</text>

  <!-- Card 4: Architecture Focus -->
  <rect x="604" y="70" width="172" height="85" rx="10" fill="#161B22" stroke="#30363D" stroke-width="1"/>
  <text x="620" y="98" class="metric-lbl">⚡ Core Philosophy</text>
  <text x="620" y="132" class="metric-val" style="fill: #A855F7; font-size: 17px;">Local-First</text>

  <!-- Bottom Language Distribution Header -->
  <text x="24" y="182" class="sub" style="font-weight: 600; fill: #C9D1D9;">Primary Ecosystem Breakdown</text>
  
  <!-- Language Progress Bar -->
  <rect x="24" y="194" width="530" height="10" rx="5" fill="#F05138"/>
  <rect x="558" y="194" width="140" height="10" rx="0" fill="#3776AB"/>
  <rect x="702" y="194" width="74" height="10" rx="5" fill="#89E051"/>

  <!-- Legend -->
  <circle cx="28" cy="226" r="4" fill="#F05138"/>
  <text x="38" y="230" class="lang-lbl">Swift <tspan fill="#F0F6FC">70.5%</tspan></text>

  <circle cx="160" cy="226" r="4" fill="#3776AB"/>
  <text x="170" y="230" class="lang-lbl">Python <tspan fill="#F0F6FC">18.7%</tspan></text>

  <circle cx="290" cy="226" r="4" fill="#89E051"/>
  <text x="300" y="230" class="lang-lbl">Shell / Bash <tspan fill="#F0F6FC">10.8%</tspan></text>
</svg>"""
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"✅ Generated static GitHub stats SVG at: {svg_path}")

def main():
    initial_history_json = "{}"
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            initial_history_json = json.dumps(json.load(f), sort_keys=True)

    print("=" * 65)
    print("🚀 SyntaxSamurai Total Clones Sync (Own Repos Only - No Forks)")
    print("=" * 65)

    # 1. Discover user's own repositories
    own_repos = get_own_repositories()
    print(f"📋 Discovered {len(own_repos)} own original repositories (Forks excluded):")
    for r in own_repos:
        print(f"  • {r}")
    print("-" * 65)

    # 2. Load existing history
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    total_new_entries = 0

    # 3. Fetch traffic data for each own repo
    for repo_slug in own_repos:
        if repo_slug not in history:
            history[repo_slug] = {}

        traffic_data = fetch_traffic_clones(repo_slug)
        if not traffic_data:
            continue

        clones = traffic_data.get("clones", [])
        for entry in clones:
            timestamp = entry.get("timestamp")
            count = entry.get("count", 0)
            if not timestamp:
                continue

            # Update count if new or higher than previous record
            if timestamp not in history[repo_slug] or count > history[repo_slug][timestamp]:
                history[repo_slug][timestamp] = count
                total_new_entries += 1

    # 4. Save updated history
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, sort_keys=True)

    # 5. Calculate per-repo and grand total clones
    print("\n📊 Current Clones Breakdown:")
    grand_total = 0
    for repo_slug, days in sorted(history.items()):
        repo_sum = sum(days.values())
        grand_total += repo_sum
        print(f"  • {repo_slug:<40}: {repo_sum:>4} clones ({len(days)} recorded dates)")

    print("=" * 65)
    print(f"🔥 Grand Total Clones (Own Repos): {grand_total} (+{total_new_entries} updates)")
    print("=" * 65)

    # 6. Generate static GitHub stats SVG
    generate_stats_svg(grand_total, len(own_repos))

    # 7. Update README.md badge
    if not os.path.exists(README_FILE):
        print(f"Error: README.md not found at {README_FILE}")
        sys.exit(1)

    with open(README_FILE, "r", encoding="utf-8") as f:
        readme_content = f.read()

    # Match badge format: Total_Clones-<number>-00FF66 or Total_Clones-<number>%2B-00FF66
    pattern = r"Total_Clones-[^-\?]+-00FF66"
    replacement = f"Total_Clones-{grand_total}-00FF66"

    new_readme, num_subs = re.subn(pattern, replacement, readme_content)
    if num_subs == 0:
        print("⚠️ Warning: Total_Clones badge pattern not found in README.md.")
    else:
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(new_readme)
        print(f"✅ README.md badge updated to: Total_Clones-{grand_total}-00FF66")

    history_changed = (json.dumps(history, sort_keys=True) != initial_history_json)
    readme_changed = (new_readme != readme_content)

    print("\n🔍 Status:")
    print(f"  • Clones History Changed: {history_changed}")
    print(f"  • README Badge Changed:   {readme_changed}")

    # 8. Commit and push if running locally and changes exist
    is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    if not is_ci:
        if history_changed or readme_changed:
            print("\n📦 Local execution: Syncing with remote, committing and pushing changes...")
            run_cmd("git pull --rebase origin main")
            run_cmd("git add README.md clones_history.json assets/github_stats.svg")
            commit_msg = f"docs: auto update clone count to {grand_total}"
            out, err = run_cmd(f'git commit -m "{commit_msg}"')
            if err and "nothing to commit" not in err:
                print(f"Commit note: {err}")
            else:
                print(f"✅ Committed: {commit_msg}")
            
            p_out, p_err = run_cmd("git push origin main")
            if p_err and "Everything up-to-date" not in p_err:
                print(f"Push info: {p_err or p_out}")
            else:
                print("🚀 Pushed updates to GitHub origin main successfully!")
        else:
            print("\n✨ Everything is up to date. No git commit needed.")
    else:
        print("\n🤖 Running in GitHub Actions CI environment. Workflow will handle git commit/push if needed.")

    print("\n🎉 Done!")

if __name__ == "__main__":
    main()

