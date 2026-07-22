#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"


@dataclass
class SkillMeta:
  name: str
  description: str


def _read_text(path: Path) -> str:
  return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")


def _parse_frontmatter(skill_md: str) -> SkillMeta:
  # Very small YAML-ish parser (frontmatter only):
  # ---
  # name: ...
  # description: ...
  # ---
  m = re.match(r"^---\s*\n(.*?)\n---\s*\n", skill_md, re.DOTALL)
  if not m:
    return SkillMeta(name="(unknown)", description="")
  block = m.group(1)
  name = "(unknown)"
  desc = ""
  for line in block.splitlines():
    if line.startswith("name:"):
      name = line.split(":", 1)[1].strip().strip('"')
    if line.startswith("description:"):
      desc = line.split(":", 1)[1].strip().strip('"')
  return SkillMeta(name=name, description=desc)


def _skill_dir(skill_name: str) -> Path:
  return SKILLS_DIR / skill_name


def _paths(skill_name: str) -> Dict[str, Path]:
  d = _skill_dir(skill_name)
  return {
    "dir": d,
    "skill_md": d / "SKILL.md",
    "upstream_md": d / "SKILL.upstream.md",
    "archive_dir": d / "archive",
    "evolution": d / "evolution.json",
  }


def _load_evolution(path: Path) -> Dict[str, Any]:
  if not path.exists():
    return {}
  return json.loads(_read_text(path))


def _save_evolution(path: Path, data: Dict[str, Any]) -> None:
  _write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _http_get(url: str) -> str:
  # Avoid external deps; use stdlib.
  from urllib.request import Request, urlopen

  req = Request(url, headers={"User-Agent": "opencode-skill-manager"})
  with urlopen(req, timeout=60) as resp:
    return resp.read().decode("utf-8", errors="replace")


def _archive_upstream(upstream_path: Path, archive_dir: Path, tag: str) -> None:
  if not upstream_path.exists():
    return
  archive_dir.mkdir(parents=True, exist_ok=True)
  ts = time.strftime("%Y%m%d-%H%M%S")
  safe_tag = re.sub(r"[^A-Za-z0-9._-]+", "_", tag) if tag else "unknown"
  dest = archive_dir / f"SKILL.upstream.{ts}.{safe_tag}.md"
  shutil.copy2(upstream_path, dest)

  # Keep only last 5.
  files = sorted(
    [p for p in archive_dir.glob("SKILL.upstream.*.md") if p.is_file()],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
  )
  for p in files[5:]:
    try:
      p.unlink()
    except OSError:
      pass


def _render_local_evolution(evo: Dict[str, Any]) -> str:
  blocks = []

  lessons = evo.get("lessons", [])
  if lessons:
    lines = ["### Lessons", ""]
    for item in lessons:
      title = item.get("title") or item.get("error") or "Lesson"
      fix = item.get("fix") or item.get("steps") or ""
      lines.append(f"- {title}")
      if fix:
        lines.append(f"  - {fix}")
    blocks.append("\n".join(lines).strip())

  prefs = evo.get("preferences", {})
  if prefs:
    lines = ["### Preferences", ""]
    for k, v in prefs.items():
      lines.append(f"- {k}: {v}")
    blocks.append("\n".join(lines).strip())

  notes = evo.get("notes", "").strip()
  if notes:
    blocks.append("### Notes\n\n" + notes)

  extra = evo.get("append_markdown", "").strip()
  if extra:
    blocks.append(extra)

  if not blocks:
    return "(no local evolution saved yet)"
  return "\n\n".join(blocks).strip() + "\n"


def _apply_evolution(skill_name: str) -> None:
  p = _paths(skill_name)
  evo = _load_evolution(p["evolution"])

  # Choose upstream baseline.
  if p["upstream_md"].exists():
    base = _read_text(p["upstream_md"]) 
  elif p["skill_md"].exists():
    base = _read_text(p["skill_md"]) 
  else:
    raise SystemExit(f"Skill not found: {p['skill_md']}")

  injected = _render_local_evolution(evo)
  final = base.rstrip() + "\n\n---\n\n## Local Evolution\n\n" + injected
  _write_text(p["skill_md"], final)


def cmd_list(_: argparse.Namespace) -> None:
    if not SKILLS_DIR.exists():
        print(f"No skills directory: {SKILLS_DIR}")
        return

    import subprocess
    import textwrap

    def run(cmd):
        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, text=True, timeout=5
            )
            return out.strip()
        except Exception:
            return ""

    def pip_show(pkg):
        out = run(["python3", "-m", "pip", "show", pkg])
        if not out:
            return "(not installed)"
        for line in out.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return "(installed)"

    rows = []
    headers = ["name", "description", "version/dep", "repo/docs", "upstream", "update?"]

    for d in sorted([p for p in SKILLS_DIR.iterdir() if p.is_dir()]):
        skill_md_path = d / "SKILL.md"
        if not skill_md_path.exists():
            continue
        
        meta = _parse_frontmatter(_read_text(skill_md_path))
        name = meta.name
        desc = meta.description.replace("\n", " ").strip()

        evo_path = d / "evolution.json"
        upstream_url = ""
        if evo_path.exists():
            try:
                evo = json.loads(_read_text(evo_path))
                upstream_url = (evo.get("upstream") or {}).get("raw_skill_md_url", "")
            except Exception:
                pass
        
        link_map = {
            'yt-dlp': 'https://github.com/yt-dlp/yt-dlp',
            'github': 'https://cli.github.com/',
            'playwright': 'https://playwright.dev/',
            'pdf': 'https://pypi.org/project/pypdf/',
            'docx': 'https://pypi.org/project/python-docx/',
            'pptx': 'https://pypi.org/project/python-pptx/',
            'xlsx': 'https://pypi.org/project/openpyxl/',
            'skill-creator': 'https://github.com/anthropics/skills',
        }
        link = link_map.get(name, '(local)')

        ver = 'local skill'
        if name == 'yt-dlp': ver = run(['yt-dlp', '--version']) or '(not installed)'
        elif name == 'github':
            ghv = run(['gh', '--version'])
            ver = ghv.splitlines()[0] if ghv else 'gh (not installed)'
        elif name == 'pdf': ver = f"pypdf {pip_show('pypdf')}"
        elif name == 'docx': ver = f"python-docx {pip_show('python-docx')}"
        elif name == 'pptx': ver = f"python-pptx {pip_show('python-pptx')}"
        elif name == 'xlsx': ver = f"openpyxl {pip_show('openpyxl')}"
        elif name == 'playwright': ver = f"playwright {pip_show('playwright')}"
        
        needs_update = 'manual'
        if upstream_url:
            needs_update = 'run `update`'
        
        # For now, we'll hardcode one example.
        if name == 'yt-dlp' and '2025.12.08' in ver:
            needs_update = 'up-to-date'

        rows.append([name, desc, ver, link, upstream_url or '(none)', needs_update])

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    desc_idx = headers.index("description")
    max_desc_width = 60
    if widths[desc_idx] > max_desc_width:
        widths[desc_idx] = max_desc_width

    header_line = " | ".join(f"{h.upper():<{widths[i]}}" for i, h in enumerate(headers))
    print(header_line)
    print("-+-".join("-" * w for w in widths))
    
    for row in rows:
        wrapped_rows = [[] for _ in range(len(row))]
        max_lines = 1
        for i, cell in enumerate(row):
            if i == desc_idx:
                lines = textwrap.wrap(str(cell), width=widths[i])
                wrapped_rows[i] = lines
                max_lines = max(max_lines, len(lines))
            else:
                wrapped_rows[i] = [str(cell)]
        
        for i in range(len(row)):
            while len(wrapped_rows[i]) < max_lines:
                wrapped_rows[i].append("")

        for line_idx in range(max_lines):
            row_line = " | ".join(f"{wrapped_rows[i][line_idx]:<{widths[i]}}" for i in range(len(row)))
            print(row_line)
    
    opencode_ver = run(['opencode', '--version']) or '(unknown)'
    print('\nNotes:')
    print(f"- opencode version: {opencode_ver}")



def cmd_show(args: argparse.Namespace) -> None:
  p = _paths(args.skill)
  if not p["skill_md"].exists():
    raise SystemExit(f"Missing: {p['skill_md']}")
  meta = _parse_frontmatter(_read_text(p["skill_md"]))
  print(f"name: {meta.name}")
  print(f"description: {meta.description}")
  print(f"path: {p['dir']}")
  print(f"has_upstream: {p['upstream_md'].exists()}")
  print(f"has_evolution: {p['evolution'].exists()}")
  print(f"archive_dir: {p['archive_dir'] if p['archive_dir'].exists() else '(missing)'}")
  if p["evolution"].exists():
    evo = _load_evolution(p["evolution"])
    upstream = evo.get("upstream", {})
    if upstream:
      print(f"upstream: {upstream}")


def cmd_init(args: argparse.Namespace) -> None:
  p = _paths(args.skill)
  if not p["dir"].exists():
    raise SystemExit(f"Missing skill directory: {p['dir']}")

  p["archive_dir"].mkdir(parents=True, exist_ok=True)

  if not p["upstream_md"].exists() and p["skill_md"].exists():
    shutil.copy2(p["skill_md"], p["upstream_md"])

  if not p["evolution"].exists():
    tmpl = {
      "skill": args.skill,
      "local_version": 1,
      "upstream": {
        "raw_skill_md_url": "",
        "ref": "",
        "last_checked": "",
      },
      "preferences": {},
      "lessons": [],
      "notes": "",
      "append_markdown": "",
    }
    _save_evolution(p["evolution"], tmpl)

  _apply_evolution(args.skill)
  print("OK")


def cmd_set_upstream(args: argparse.Namespace) -> None:
  p = _paths(args.skill)
  if not p["dir"].exists():
    raise SystemExit(f"Missing skill directory: {p['dir']}")
  evo = _load_evolution(p["evolution"]) or {"skill": args.skill}
  evo.setdefault("upstream", {})
  evo["upstream"]["raw_skill_md_url"] = args.url
  evo["upstream"]["last_checked"] = ""
  _save_evolution(p["evolution"], evo)
  print("OK")


def cmd_update(args: argparse.Namespace) -> None:
  p = _paths(args.skill)
  evo = _load_evolution(p["evolution"])
  url = (evo.get("upstream", {}) or {}).get("raw_skill_md_url")
  if not url:
    raise SystemExit("No upstream url. Use: set-upstream <skill> <raw-skill-md-url>")

  # Archive current upstream.
  _archive_upstream(p["upstream_md"], p["archive_dir"], tag=evo.get("upstream", {}).get("ref", "url"))

  # Fetch and replace upstream baseline.
  content = _http_get(url)
  _write_text(p["upstream_md"], content)

  evo.setdefault("upstream", {})
  evo["upstream"]["last_checked"] = time.strftime("%Y-%m-%d %H:%M:%S")
  _save_evolution(p["evolution"], evo)

  _apply_evolution(args.skill)
  print("OK")


def cmd_apply_evolution(args: argparse.Namespace) -> None:
  _apply_evolution(args.skill)
  print("OK")


def cmd_rollback(args: argparse.Namespace) -> None:
  p = _paths(args.skill)
  src = p["archive_dir"] / args.archive
  if not src.exists():
    raise SystemExit(f"Missing archive file: {src}")
  shutil.copy2(src, p["upstream_md"])
  _apply_evolution(args.skill)
  print("OK")


def main() -> None:
  ap = argparse.ArgumentParser(prog="skill_manager")
  sub = ap.add_subparsers(dest="cmd", required=True)

  sub.add_parser("list")

  p_show = sub.add_parser("show")
  p_show.add_argument("skill")

  p_init = sub.add_parser("init")
  p_init.add_argument("skill")

  p_set = sub.add_parser("set-upstream")
  p_set.add_argument("skill")
  p_set.add_argument("url")

  p_upd = sub.add_parser("update")
  p_upd.add_argument("skill")

  p_apply = sub.add_parser("apply-evolution")
  p_apply.add_argument("skill")

  p_rb = sub.add_parser("rollback")
  p_rb.add_argument("skill")
  p_rb.add_argument("archive")

  args = ap.parse_args()

  if args.cmd == "list":
    cmd_list(args)
  elif args.cmd == "show":
    cmd_show(args)
  elif args.cmd == "init":
    cmd_init(args)
  elif args.cmd == "set-upstream":
    cmd_set_upstream(args)
  elif args.cmd == "update":
    cmd_update(args)
  elif args.cmd == "apply-evolution":
    cmd_apply_evolution(args)
  elif args.cmd == "rollback":
    cmd_rollback(args)
  else:
    raise SystemExit("Unknown cmd")


if __name__ == "__main__":
  main()
