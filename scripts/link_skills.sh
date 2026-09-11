#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_AGENTS="$REPO_ROOT/.agents/skills"
DST_CLAUDE="$REPO_ROOT/.claude/skills"
DST_OPENCODE="$REPO_ROOT/.opencode/commands"

log() { printf '[link-skills] %s\n' "$*"; }

rm_link() {
  local path="$1"
  if [ -L "$path" ] || [ -e "$path" ]; then
    rm -rf "$path"
  fi
}

# Collect sources into temp files: name<TAB>path. legacy first, .agents overrides.
src_map="$(mktemp -t linkskills)"
trap 'rm -f "$src_map"' EXIT
for d in "$SRC_AGENTS"/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  printf '%s\t%s\n' "$name" "${d%/}"
done | sort -u > "$src_map"

# Collect valid source paths (dir + file) into newline-separated list for grep -F matching.
valid_sources="$(mktemp -t linkskills-src)"
trap 'rm -f "$src_map" "$valid_sources"' EXIT
awk -F'\t' '{print $2; print $2 "/SKILL.md"}' "$src_map" > "$valid_sources"

mkdir -p "$DST_CLAUDE" "$DST_OPENCODE"

# Prune stale symlinks in destinations that point to a source no longer in src_map.
prune_stale_symlink() {
  local link="$1"
  local expected_dir="$2"
  [ -L "$link" ] || return 0
  local target abs_target
  target="$(readlink "$link")"
  if [ "${target:0:1}" = "/" ]; then
    abs_target="$target"
  else
    rel_dir="$(dirname "$target")"
    base="$(basename "$target")"
    if [ "$rel_dir" = "." ]; then
      abs_target="$expected_dir/$base"
    elif [ -d "$expected_dir/$rel_dir" ]; then
      abs_target="$(cd "$expected_dir/$rel_dir" && pwd)/$base"
    else
      abs_target="$expected_dir/$target"
    fi
  fi
  if ! grep -Fqx "$abs_target" "$valid_sources"; then
    rm_link "$link"
    log "prune stale $(basename "$link") -> $abs_target"
  fi
}

if [ -d "$DST_CLAUDE" ]; then
  for link in "$DST_CLAUDE"/*; do
    [ -L "$link" ] || continue
    prune_stale_symlink "$link" "$DST_CLAUDE"
  done
fi
if [ -d "$DST_OPENCODE" ]; then
  for link in "$DST_OPENCODE"/*.md; do
    [ -L "$link" ] || continue
    prune_stale_symlink "$link" "$DST_OPENCODE"
  done
fi

while IFS="$(printf '\t')" read -r name src; do
  skill_md="$src/SKILL.md"
  [ -f "$skill_md" ] || { log "skip $name (no SKILL.md)"; continue; }

  # .claude: directory symlink
  claude_link="$DST_CLAUDE/$name"
  if [ -L "$claude_link" ]; then
    target="$(readlink "$claude_link")"
    abs_target="$(cd "$DST_CLAUDE" && cd "$target" 2>/dev/null && pwd || true)"
    [ "$abs_target" = "$src" ] || { rm_link "$claude_link"; ln -s "../../.agents/skills/$name" "$claude_link"; log "relink $name -> $src"; }
  elif [ -e "$claude_link" ]; then
    if [ -d "$claude_link" ]; then
      log "skip $name (.claude: real dir exists)"
    else
      log "skip $name (.claude: real file exists)"
    fi
  else
    ln -s "../../.agents/skills/$name" "$claude_link"
    log "link .claude/$name -> $src"
  fi

  # .opencode: file symlink to SKILL.md
  oc_link="$DST_OPENCODE/$name.md"
  if [ -L "$oc_link" ]; then
    target="$(readlink "$oc_link")"
    abs_target="$(cd "$DST_OPENCODE" && cd "$(dirname "$target")" && pwd)/$(basename "$target")"
    [ "$abs_target" = "$skill_md" ] || { rm_link "$oc_link"; ln -s "../../.agents/skills/$name/SKILL.md" "$oc_link"; log "relink $name.md -> $skill_md"; }
  elif [ -e "$oc_link" ]; then
    log "skip $name.md (.opencode: real file exists)"
  else
    ln -s "../../.agents/skills/$name/SKILL.md" "$oc_link"
    log "link .opencode/$name.md -> $skill_md"
  fi
done < "$src_map"

log "done"

# Summary: count actions taken.
pruned_count=0
linked_count=0
[ -d "$DST_CLAUDE" ] && pruned_count=$((pruned_count + $(find "$DST_CLAUDE" -maxdepth 1 -type l | wc -l | tr -d ' ')))
[ -d "$DST_OPENCODE" ] && linked_count=$(find "$DST_OPENCODE" -maxdepth 1 -type l -name '*.md' | wc -l | tr -d ' ')
log "summary: ${linked_count} opencode skills linked"
