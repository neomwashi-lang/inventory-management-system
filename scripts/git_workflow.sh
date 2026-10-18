#!/usr/bin/env bash
# Builds a proper feature-branch + pull-request history on GitHub.
#
# Usage:  ./scripts/git_workflow.sh https://github.com/<you>/<repo>.git
#
# Run from the project root with all project files present and UNcommitted
# (do not run `git init` yourself). Create an EMPTY repo on GitHub first.
# If the GitHub CLI (`gh`) is installed and logged in, pull requests are
# created and merged automatically; otherwise the script pauses so you can
# open/merge each PR in the browser.
set -euo pipefail

REPO_URL="${1:?Usage: $0 <github-repo-url>}"
[ -f run.py ] || { echo "Run this from the project root."; exit 1; }

git init -b main >/dev/null 2>&1 || true
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"

# --- initial commit on main -------------------------------------------------
git add .gitignore requirements.txt pytest.ini
git commit -m "chore: initial project setup (gitignore, requirements, pytest config)"
git push -u origin main

feature() {  # feature <branch> <commit message> <files...>
  local branch="$1" msg="$2"; shift 2
  git checkout -b "$branch"
  git add "$@"
  git commit -m "$msg"
  git push -u origin "$branch"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh pr create --base main --head "$branch" --title "$msg" --body "Adds: $*"
    gh pr merge "$branch" --merge --delete-branch
  else
    echo
    echo ">>> Open a pull request for '$branch' on GitHub, merge it, delete the branch,"
    read -r -p ">>> then press Enter to continue... "
  fi
  # Make sure the PR really was merged before leaving the branch; otherwise the
  # feature files would disappear from your working folder.
  git fetch origin main
  if ! git merge-base --is-ancestor "$branch" origin/main; then
    echo "!! '$branch' is not merged into main yet. Merge the pull request on GitHub,"
    echo "!! then re-run:  git checkout main && git pull origin main"
    echo "!! (your files are safe on branch '$branch')"
    exit 1
  fi
  git checkout main
  git pull origin main
  git branch -D "$branch" >/dev/null 2>&1 || true
  git push origin --delete "$branch" >/dev/null 2>&1 || true   # no-op if already deleted
}

feature feature/storage-and-validation \
  "feat: add array-based mock database and input validation" \
  app/storage.py app/validators.py tests/test_storage.py

feature feature/openfoodfacts-client \
  "feat: add OpenFoodFacts client (barcode and name lookup)" \
  app/off_client.py tests/test_off_client.py

feature feature/flask-crud-api \
  "feat: add Flask CRUD routes, import/enrich and helper routes" \
  app/__init__.py app/routes.py run.py tests/conftest.py tests/test_api.py

feature feature/cli-frontend \
  "feat: add CLI with commands and interactive menu" \
  cli.py tests/test_cli.py

feature docs/readme-and-design \
  "docs: add README, design document, Postman collection and git script" \
  README.md docs scripts

echo "Done. Your repo now has main plus 5 merged pull requests."
