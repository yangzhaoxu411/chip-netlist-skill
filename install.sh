#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="chip-netlist"
TARGET="${TARGET:-codex}"
REPO_URL="${CHIP_NETLIST_REPO_URL:-https://github.com/yangzhaoxu411/chip-netlist-skill.git}"
BRANCH="${CHIP_NETLIST_BRANCH:-main}"
SOURCE="${CHIP_NETLIST_SOURCE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    --repo)
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --source)
      SOURCE="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: install.sh [--target codex|claude|opencode|all] [--repo URL] [--branch main] [--source DIR]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

target_path() {
  local name="$1"
  if [[ -n "${CHIP_NETLIST_INSTALL_ROOT:-}" ]]; then
    case "$name" in
      codex) echo "$CHIP_NETLIST_INSTALL_ROOT/codex/skills/$SKILL_NAME" ;;
      claude) echo "$CHIP_NETLIST_INSTALL_ROOT/claude/skills/$SKILL_NAME" ;;
      opencode) echo "$CHIP_NETLIST_INSTALL_ROOT/opencode/skill/$SKILL_NAME" ;;
      *) echo "Unknown target: $name" >&2; return 2 ;;
    esac
    return
  fi

  case "$name" in
    codex) echo "$HOME/.codex/skills/$SKILL_NAME" ;;
    claude) echo "$HOME/.claude/skills/$SKILL_NAME" ;;
    opencode) echo "$HOME/.config/opencode/skill/$SKILL_NAME" ;;
    *) echo "Unknown target: $name" >&2; return 2 ;;
  esac
}

resolve_source() {
  if [[ -n "$SOURCE" ]]; then
    if [[ -f "$SOURCE/$SKILL_NAME/SKILL.md" ]]; then
      (cd "$SOURCE/$SKILL_NAME" && pwd)
      return
    fi
    if [[ -f "$SOURCE/SKILL.md" ]]; then
      (cd "$SOURCE" && pwd)
      return
    fi
    echo "Source does not contain $SKILL_NAME/SKILL.md or SKILL.md: $SOURCE" >&2
    exit 1
  fi

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "$script_dir/$SKILL_NAME/SKILL.md" ]]; then
    echo "$script_dir/$SKILL_NAME"
    return
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required for remote installation. Install git or clone the repo manually." >&2
    exit 1
  fi

  local temp
  temp="$(mktemp -d)"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$temp" >/dev/null
  if [[ ! -f "$temp/$SKILL_NAME/SKILL.md" ]]; then
    echo "Cloned repository does not contain $SKILL_NAME/SKILL.md" >&2
    exit 1
  fi
  echo "$temp/$SKILL_NAME"
}

install_one() {
  local name="$1"
  local source_dir="$2"
  local dest
  dest="$(target_path "$name")"
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -R "$source_dir" "$dest"
  echo "Installed $SKILL_NAME for $name -> $dest"
}

case "$TARGET" in
  codex|claude|opencode|all) ;;
  *) echo "Invalid target: $TARGET" >&2; exit 2 ;;
esac

skill_source="$(resolve_source)"
if [[ "$TARGET" == "all" ]]; then
  install_one codex "$skill_source"
  install_one claude "$skill_source"
  install_one opencode "$skill_source"
else
  install_one "$TARGET" "$skill_source"
fi

echo "Done. Restart the target agent so it can discover $SKILL_NAME."

