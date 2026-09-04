---
# Claude Code (skill)
name: llm-wiki-release
description: 'Release llm-wiki-base (stable + beta) theo SemVer + Conventional Commits + Keep a Changelog, chỉ dùng git và gh CLI'
# Cursor (.mdc / rule)
alwaysApply: false
globs: ["pyproject.toml", "src/llm_wiki/__init__.py", "CHANGELOG.md"]
# Windsurf
trigger: release
# Kiro
inclusion: fileMatch
fileMatchPattern: "CHANGELOG.md,pyproject.toml"
# GitHub Copilot (.github/instructions/*.instructions.md)
applyTo: "pyproject.toml,CHANGELOG.md"
---
# LLM Wiki Release

Quy trình release chuẩn toàn cầu cho repo này, chỉ dùng `git` + `gh`:
[SemVer 2.0.0](https://semver.org) + [Conventional Commits 1.0.0](https://www.conventionalcommits.org) + [Keep a Changelog 1.1.0](https://keepachangelog.com). Tag quy ước `vX.Y.Z` (khớp `llm-wiki upgrade`).

## 0. Preconditions — check trước mọi thứ

```bash
git status --short          # phải trống (không commit rác, không file môi trường)
git branch --show-current   # phải là main
git fetch origin && git log --oneline origin/main -1 && git log --oneline -1
# hai dòng trên phải cùng commit (main đã sync, không release từ branch)
gh auth status              # phải logged in
python3 -m pytest tests/ -q # phải xanh
```

Version có HAI nguồn phải khớp nhau: `pyproject.toml` (`version =`) và `src/llm_wiki/__init__.py` (`__version__ =`).

## 1. Chốt số version (SemVer)

- Lần đầu: `v0.1.0` (`0.x` = API chưa ổn định, `1.0.0` khi public API ổn định).
- Sau đó, đọc `git log <tag-cũ>..HEAD --oneline`: `feat` → MINOR, `fix`/`perf` → PATCH, `!` hoặc `BREAKING CHANGE` → MAJOR.
- Không đoán: liệt kê commits cho user nếu không rõ loại thay đổi.

## 2. Bump version (cả hai file, một commit riêng nếu cần)

```bash
NEW=X.Y.Z
python3 - "$NEW" <<'EOF'
import re, sys
from pathlib import Path
new = sys.argv[1]
p = Path("pyproject.toml"); s = p.read_text()
p.write_text(re.sub(r'^version = ".*"$', f'version = "{new}"', s, count=1, flags=re.M))
i = Path("src/llm_wiki/__init__.py"); s = i.read_text()
i.write_text(re.sub(r'^__version__ = ".*"$', f'__version__ = "{new}"', s, count=1, flags=re.M))
EOF
grep -n 'version =\|__version__' pyproject.toml src/llm_wiki/__init__.py
# hai dòng in ra phải cùng X.Y.Z rồi mới đi tiếp
```

## 3. CHANGELOG.md (Keep a Changelog)

Chưa có file thì tạo khung `## [Unreleased]` + `## [X.Y.Z] - YYYY-MM-DD` với nhóm `Added/Changed/Fixed`. Tóm từ conventional commits, viết cho user (không paste log thô).

## 4. Commit release

```bash
git add pyproject.toml src/llm_wiki/__init__.py CHANGELOG.md
git status --short   # chỉ 3 file trên
git commit -m "chore(release): vX.Y.Z"
```

## 5. Tag (annotated, trên main, sau commit)

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git show vX.Y.Z --stat | head -n 10   # verify tag trỏ đúng commit release
```

## 6. Push (không bao giờ --force main/tags)

```bash
git push origin main
git push origin vX.Y.Z
```

## 7. GitHub Release (gh CLI)

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "Tóm tắt từ CHANGELOG:
- ...
- ..."
gh release view vX.Y.Z   # verify
```

## 7b. Beta release (prerelease, khi cần thử nghiệm trước stable)

Đánh số SemVer prerelease `X.Y.Z-beta.N` (`beta.1`, `beta.2`, ... cho cùng target stable; precedence thấp hơn stable nên không bao giờ thành `latest`).

```bash
NEW=X.Y.ZbN   # file version dùng dạng PEP 440 cho pip-safe (vd 0.2.0b1)
# bump 2 file version như bước 2, CHANGELOG ghi mục ## [X.Y.Z-beta.N]
git add pyproject.toml src/llm_wiki/__init__.py CHANGELOG.md
git commit -m "chore(release): vX.Y.Z-beta.N"
git tag -a vX.Y.Z-beta.N -m "vX.Y.Z-beta.N"
git push origin main && git push origin vX.Y.Z-beta.N
gh release create vX.Y.Z-beta.N --prerelease --title "vX.Y.Z-beta.N" --notes "Beta, cần thử:
- ...
- ..."
gh release view vX.Y.Z-beta.N   # verify, phải hiện `Pre-release`
```

Lưu ý:

- File version (`X.Y.ZbN`) và tag/release (`vX.Y.Z-beta.N`) khác dạng nhau là cố ý: pip chỉ hiểu PEP 440, GitHub chỉ nhận prerelease SemVer có gạch ngang.
- `llm-wiki upgrade --to latest` bỏ qua beta theo thiết kế (chỉ match `vX.Y.Z` stable). Muốn thử beta: `git checkout vX.Y.Z-beta.N` (+ cài lại nếu không editable) rồi kiểm thủ công; `--to <beta>` hiện chưa hỗ trợ.
- Lên stable: làm tiếp quy trình thường (bước 2–7) với `X.Y.Z`, CHANGELOG gộp mục beta vào mục stable. Không xóa beta release/tag sau khi stable ra (giữ lịch sử thử nghiệm).

## 8. Post-release

- `llm-wiki status` ở máy khác phải thấy latest mới.
- Hỏng release: `gh release delete vX.Y.Z --yes && git push origin :vX.Y.Z && git tag -d vX.Y.Z`, sửa, làm lại từ bước 2 với PATCH+1. Không bao giờ dời tag đã có người dùng.

## Cấm

- Tag/commit release từ feature branch. Viết lại history đã push (`rebase/push --force/amend` sau push). Tag lightweight (thiếu `-a`, mất message/ngày). Release khi test đỏ hoặc tree bẩn.
