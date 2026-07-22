#!/usr/bin/env python3
"""Plan, apply, and roll back Skill Atlas updates with explicit confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Iterator

import security_review_skills


SKILL_NAME = "skill-atlas"
EXCLUDED_NAMES = {".git", "__pycache__", ".DS_Store"}


class UpdateError(RuntimeError):
    """Raised when an update cannot pass validation or be applied safely."""


def load_metadata(root: Path) -> dict[str, Any]:
    path = root / "skill.json"
    if not path.is_file():
        raise UpdateError(f"missing metadata: {path}")
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateError(f"invalid metadata: {path}: {exc}") from exc
    if metadata.get("name") != SKILL_NAME:
        raise UpdateError(f"unexpected skill name: {metadata.get('name')!r}")
    if not metadata.get("version"):
        raise UpdateError("skill.json must contain a version")
    return metadata


def iter_package_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.is_file() and not path.is_symlink():
            yield path


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_package_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_key(value: str) -> tuple[tuple[int, ...], int, str]:
    base, separator, suffix = value.partition("-")
    try:
        numbers = tuple(int(part) for part in base.split("."))
    except ValueError:
        numbers = ()
    return numbers, 0 if separator else 1, suffix


def version_relation(current: str, candidate: str) -> str:
    if current == candidate:
        return "same"
    current_key = version_key(current)
    candidate_key = version_key(candidate)
    if current_key[0] and candidate_key[0]:
        return "newer" if candidate_key > current_key else "older"
    return "different"


def ensure_safe_member(destination: Path, member_name: str) -> None:
    member = (destination / member_name).resolve()
    destination = destination.resolve()
    if member != destination and destination not in member.parents:
        raise UpdateError(f"archive contains an unsafe path: {member_name}")


def extract_archive(source: Path, destination: Path) -> None:
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                ensure_safe_member(destination, info.filename)
                mode = info.external_attr >> 16
                if mode and (mode & 0o170000) == 0o120000:
                    raise UpdateError(f"archive contains a symlink: {info.filename}")
            archive.extractall(destination)
        return
    if tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            for member in archive.getmembers():
                ensure_safe_member(destination, member.name)
                if member.issym() or member.islnk():
                    raise UpdateError(f"archive contains a link: {member.name}")
                if not member.isfile() and not member.isdir():
                    raise UpdateError(f"archive contains an unsupported entry: {member.name}")
            archive.extractall(destination)
        return
    raise UpdateError(f"unsupported archive: {source}")


def locate_skill_root(root: Path) -> Path:
    if (root / "SKILL.md").is_file() and (root / "skill.json").is_file():
        return root
    matches = [
        path.parent
        for path in root.rglob("skill.json")
        if (path.parent / "SKILL.md").is_file()
    ]
    if len(matches) != 1:
        raise UpdateError(f"expected exactly one Skill Atlas package, found {len(matches)}")
    return matches[0]


def prepare_source(source: Path, checksum: str | None) -> tuple[tempfile.TemporaryDirectory[str] | None, Path, str]:
    source = source.expanduser().resolve()
    if not source.exists():
        raise UpdateError(f"source does not exist: {source}")
    if source.is_dir():
        if checksum and tree_sha256(source) != checksum.lower():
            raise UpdateError("source directory checksum does not match --checksum")
        return None, locate_skill_root(source), "directory"
    actual_checksum = file_sha256(source)
    if not checksum:
        raise UpdateError("archive updates require --checksum SHA256")
    if actual_checksum != checksum.lower():
        raise UpdateError("archive checksum does not match --checksum")
    temporary = tempfile.TemporaryDirectory(prefix="skill-atlas-source-")
    extract_archive(source, Path(temporary.name))
    return temporary, locate_skill_root(Path(temporary.name)), "archive"


def security_result(root: Path) -> dict[str, Any]:
    findings = security_review_skills.review_target(root, strict=True)
    return {
        "verdict": security_review_skills.verdict(findings),
        "finding_count": len(findings),
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "file": str(Path(finding.file).relative_to(root)),
                "line": finding.line,
                "reason": finding.reason,
            }
            for finding in findings
        ],
    }


def backup_root_for(install_root: Path) -> Path:
    return install_root.parent / f".{SKILL_NAME}-backups"


def candidate_status(install_root: Path, source: Path | None, checksum: str | None) -> dict[str, Any]:
    current = load_metadata(install_root)
    result: dict[str, Any] = {
        "action": "self-status",
        "installed_path": str(install_root),
        "current_version": current["version"],
        "channel": current.get("channel", "stable"),
        "update_policy": current.get("update_policy", "notify"),
        "repository": current.get("repository"),
        "current_sha256": tree_sha256(install_root),
        "read_only": True,
    }
    if source is None:
        result.update(
            {
                "status": "source-not-configured" if not current.get("repository") else "remote-check-not-implemented",
                "message": "Provide --source with a reviewed local directory or archive to check a release.",
            }
        )
        return result
    temporary, candidate_root, source_type = prepare_source(source, checksum)
    try:
        candidate = load_metadata(candidate_root)
        review = security_result(candidate_root)
        candidate_hash = tree_sha256(candidate_root)
        relation = version_relation(current["version"], candidate["version"])
        result.update(
            {
                "status": "candidate-reviewed",
                "source": str(source.expanduser().resolve()),
                "source_type": source_type,
                "candidate_version": candidate["version"],
                "version_relation": relation,
                "candidate_sha256": candidate_hash,
                "security": review,
                "eligible_to_apply": review["verdict"] == "safe"
                and relation in {"newer", "different"}
                and candidate_hash != result["current_sha256"],
            }
        )
    finally:
        if temporary:
            temporary.cleanup()
    return result


def copy_candidate(candidate_root: Path, destination: Path) -> None:
    shutil.copytree(
        candidate_root,
        destination,
        symlinks=False,
        ignore=shutil.ignore_patterns(*EXCLUDED_NAMES),
    )


def atomic_install(install_root: Path, candidate_root: Path, backup_root: Path) -> Path:
    install_parent = install_root.parent
    install_parent.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
    current_version = load_metadata(install_root)["version"]
    backup = backup_root / f"{stamp}-{current_version}-{tree_sha256(install_root)[:12]}"
    staged = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}-stage-", dir=install_parent))
    displaced = install_parent / f".{SKILL_NAME}-previous-{os.getpid()}"
    try:
        staged.rmdir()
        copy_candidate(candidate_root, staged)
        install_root.rename(displaced)
        try:
            staged.rename(install_root)
        except Exception:
            displaced.rename(install_root)
            raise
        displaced.rename(backup)
    except Exception:
        if displaced.exists() and not install_root.exists():
            displaced.rename(install_root)
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return backup


def apply_update(install_root: Path, source: Path, checksum: str | None) -> dict[str, Any]:
    temporary, candidate_root, source_type = prepare_source(source, checksum)
    try:
        current = load_metadata(install_root)
        candidate = load_metadata(candidate_root)
        review = security_result(candidate_root)
        if review["verdict"] != "safe":
            raise UpdateError(f"candidate security verdict is {review['verdict']}; update refused")
        relation = version_relation(current["version"], candidate["version"])
        if relation == "same":
            raise UpdateError("candidate version matches the installed version")
        if relation == "older":
            raise UpdateError("candidate version is older; use rollback for downgrades")
        backup = atomic_install(install_root, candidate_root, backup_root_for(install_root))
        return {
            "action": "self-update",
            "status": "updated",
            "source_type": source_type,
            "previous_version": current["version"],
            "installed_version": candidate["version"],
            "installed_path": str(install_root),
            "backup_path": str(backup),
            "rollback_command": f"manage self rollback --backup {backup} --apply --confirm",
        }
    finally:
        if temporary:
            temporary.cleanup()


def list_backups(install_root: Path) -> list[dict[str, Any]]:
    root = backup_root_for(install_root)
    if not root.is_dir():
        return []
    backups = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        try:
            metadata = load_metadata(path)
        except UpdateError:
            continue
        backups.append({"path": str(path), "version": metadata["version"], "sha256": tree_sha256(path)})
    return backups


def resolve_backup(install_root: Path, value: str) -> Path:
    backup_root = backup_root_for(install_root).resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = backup_root / candidate
    candidate = candidate.resolve()
    if backup_root not in candidate.parents or not candidate.is_dir():
        raise UpdateError("backup must be an existing directory inside the managed backup root")
    load_metadata(candidate)
    return candidate


def apply_rollback(install_root: Path, backup_value: str) -> dict[str, Any]:
    backup = resolve_backup(install_root, backup_value)
    review = security_result(backup)
    if review["verdict"] != "safe":
        raise UpdateError(f"backup security verdict is {review['verdict']}; rollback refused")
    target_version = load_metadata(backup)["version"]
    recovery = atomic_install(install_root, backup, backup_root_for(install_root))
    return {
        "action": "self-rollback",
        "status": "rolled-back",
        "installed_version": target_version,
        "installed_path": str(install_root),
        "recovery_backup_path": str(recovery),
    }


def emit_markdown(result: dict[str, Any]) -> None:
    print(f"# Skill Atlas {result['action'].replace('-', ' ').title()}")
    print()
    for key, value in result.items():
        if key in {"action", "security", "backups"} or value is None:
            continue
        print(f"- {key.replace('_', ' ')}: {str(value).lower() if isinstance(value, bool) else value}")
    if "security" in result:
        print(f"- security verdict: {result['security']['verdict']}")
        print(f"- security findings: {result['security']['finding_count']}")
    if "backups" in result:
        print()
        print(f"## Backups ({len(result['backups'])})")
        print()
        for backup in result["backups"]:
            print(f"- {backup['version']}: `{backup['path']}`")


def run(args: argparse.Namespace) -> dict[str, Any]:
    install_root = Path(args.install_root).expanduser().resolve()
    if args.action == "status":
        return candidate_status(install_root, Path(args.source) if args.source else None, args.checksum)
    if args.action == "update":
        if not args.source:
            raise UpdateError("update requires --source")
        if args.apply != args.confirm:
            raise UpdateError("applying an update requires both --apply and --confirm")
        if not args.apply:
            result = candidate_status(install_root, Path(args.source), args.checksum)
            result["action"] = "self-update-plan"
            result["required_to_apply"] = ["--apply", "--confirm"]
            return result
        return apply_update(install_root, Path(args.source), args.checksum)
    if args.apply != args.confirm:
        raise UpdateError("applying a rollback requires both --apply and --confirm")
    if not args.apply:
        return {
            "action": "self-rollback-plan",
            "status": "read-only",
            "installed_path": str(install_root),
            "backups": list_backups(install_root),
            "required_to_apply": ["--backup PATH", "--apply", "--confirm"],
        }
    if not args.backup:
        raise UpdateError("rollback application requires --backup")
    return apply_rollback(install_root, args.backup)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "update", "rollback"])
    parser.add_argument("--install-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--source", help="Reviewed local release directory or archive.")
    parser.add_argument("--checksum", help="Expected SHA-256; required for archives.")
    parser.add_argument("--backup", help="Backup path or name to restore.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        result = run(args)
    except (OSError, UpdateError) as exc:
        result = {"action": f"self-{args.action}", "status": "refused", "error": str(exc)}
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            emit_markdown(result)
        raise SystemExit(2) from None
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
