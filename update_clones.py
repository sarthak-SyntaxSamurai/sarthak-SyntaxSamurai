#!/usr/bin/env python3
import json
import os
import subprocess
import re

# Use absolute paths for everything to ensure launchd can find them
REPO_DIR = "/Users/sarthakanand/Projects/new app/sarthak-SyntaxSamurai"
HISTORY_FILE = os.path.join(REPO_DIR, "clones_history.json")
README_FILE = os.path.join(REPO_DIR, "README.md")

# Ensure environment has standard paths (especially for Homebrew)
env = os.environ.copy()
env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")

def run_cmd(cmd, cwd=REPO_DIR):
    result = subprocess.run(cmd, shell=True, env=env, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {cmd}\n{result.stderr}")
        return None
    return result.stdout.strip()

def main():
    print("Fetching clone traffic data...")
    gh_output = run_cmd("gh api repos/sarthak-SyntaxSamurai/FrogDrop/traffic/clones")
    if not gh_output:
        print("Failed to fetch traffic from GitHub.")
        return

    traffic_data = json.loads(gh_output)
    
    # Load history
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except Exception as e:
            print(f"Failed to load history: {e}")
            history = {}

    # Update history with new data
    new_entries = 0
    for entry in traffic_data.get("clones", []):
        timestamp = entry["timestamp"]
        count = entry["count"]
        # Only update if count is > 0 or if we don't have it yet.
        # This prevents 0 counts from overwriting valid data if gh api gives empty day.
        if timestamp not in history or count > history[timestamp]:
            history[timestamp] = count
            new_entries += 1

    # Save history
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    # Calculate total clones
    total_clones = sum(history.values())
    print(f"Total clones tracked: {total_clones} (added {new_entries} updated days)")

    # Read README
    with open(README_FILE, "r") as f:
        readme_content = f.read()

    # Regex to find the total clones badge
    # It looks like: <img src="https://img.shields.io/badge/Total_Clones-200%2B-00FF66...
    pattern = r"Total_Clones-[^-\?]+-00FF66"
    replacement = f"Total_Clones-{total_clones}-00FF66"
    
    new_readme, num_subs = re.subn(pattern, replacement, readme_content)

    if num_subs == 0:
        print("Could not find the clone badge in README.md to replace.")
        return
        
    if new_readme == readme_content:
        print("No changes to clones, README remains the same.")
        return

    print("Updating README.md with new clone count...")
    with open(README_FILE, "w") as f:
        f.write(new_readme)

    # Git commit and push
    print("Committing to git...")
    run_cmd("git add README.md clones_history.json")
    run_cmd(f'git commit -m "docs: auto update clone count to {total_clones}"')
    run_cmd("git push origin main")
    print("Done! Profile successfully updated.")

if __name__ == "__main__":
    main()
