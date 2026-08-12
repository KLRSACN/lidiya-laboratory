#!/usr/bin/env python3
"""Update Lidiya's curated open-source radar using GitHub's public API.

This program performs metadata discovery only. It does not clone, download,
install, execute, merge, publish, or change any external project.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "registry.json"
SNAPSHOT_PATH = ROOT / "LATEST_SNAPSHOT.json"
RADAR_PATH = ROOT / "OPEN_SOURCE_RADAR.md"
API_ROOT = "https://api.github.com"
USER_AGENT = "lidiya-open-source-radar/1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def github_get(path: str, *, optional: bool = False) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(f"{API_ROOT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if optional and exc.code in {404, 409, 422}:
            return None
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub API HTTP {exc.code} for {path}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API unavailable for {path}: {exc.reason}") from exc


def freshness_score(pushed_at: str | None, archived: bool) -> tuple[int, int | None]:
    if archived:
        return 0, None
    pushed = parse_github_time(pushed_at)
    if pushed is None:
        return 4, None
    days = max(0, (utc_now() - pushed).days)
    if days <= 30:
        return 20, days
    if days <= 90:
        return 16, days
    if days <= 365:
        return 10, days
    return 4, days


def evaluate(project: dict[str, Any], repo_data: dict[str, Any]) -> dict[str, Any]:
    state = project.get("adoption_state", "observe")
    if state.startswith("existing"):
        fit_score = 20
    elif state in {"candidate", "observe_and_sandbox"}:
        fit_score = 16
    elif state == "reference_only":
        fit_score = 12
    else:
        fit_score = 8

    trust_score = 20 if project.get("trust_tier") == "official_upstream" else 17
    maintenance_score, age_days = freshness_score(
        repo_data.get("pushed_at"), bool(repo_data.get("archived"))
    )
    control_score = 18 if project.get("portable_priority") else 14
    if state == "reference_only":
        control_score = min(control_score, 12)
    resource_score = 18 if project.get("portable_priority") else 12
    if project.get("category") == "agent_runtime":
        resource_score = 10

    total = fit_score + trust_score + maintenance_score + control_score + resource_score
    if repo_data.get("archived"):
        decision = "BLOCK_ARCHIVED"
    elif not (repo_data.get("license") or {}).get("spdx_id"):
        decision = "REVIEW_LICENSE"
    elif total >= 90:
        decision = "HIGH_TRUST_CANDIDATE"
    elif total >= 75:
        decision = "CANDIDATE_INTEGRATION"
    elif total >= 60:
        decision = "SANDBOX_EVALUATION"
    elif total >= 40:
        decision = "OBSERVE"
    else:
        decision = "IGNORE"

    return {
        "score": total,
        "decision": decision,
        "dimensions": {
            "need_fit": fit_score,
            "source_trust": trust_score,
            "maintenance_health": maintenance_score,
            "control_and_rollback": control_score,
            "resource_efficiency": resource_score,
        },
        "days_since_push": age_days,
    }


def fetch_project(project: dict[str, Any]) -> dict[str, Any]:
    repo = project["repo"]
    repo_data = github_get(f"/repos/{repo}")
    release = github_get(f"/repos/{repo}/releases/latest", optional=True)
    commits = github_get(f"/repos/{repo}/commits?per_page=1", optional=True) or []
    head = commits[0] if commits else None
    evaluation = evaluate(project, repo_data)

    return {
        "repo": repo,
        "category": project.get("category"),
        "purpose": project.get("purpose"),
        "fit": project.get("fit", []),
        "adoption_state": project.get("adoption_state"),
        "portable_priority": bool(project.get("portable_priority")),
        "repository": {
            "html_url": repo_data.get("html_url"),
            "description": repo_data.get("description"),
            "default_branch": repo_data.get("default_branch"),
            "archived": bool(repo_data.get("archived")),
            "fork": bool(repo_data.get("fork")),
            "license": (repo_data.get("license") or {}).get("spdx_id"),
            "stars": repo_data.get("stargazers_count"),
            "forks": repo_data.get("forks_count"),
            "open_issues": repo_data.get("open_issues_count"),
            "pushed_at": repo_data.get("pushed_at"),
            "updated_at": repo_data.get("updated_at"),
        },
        "latest_release": None
        if release is None
        else {
            "tag": release.get("tag_name"),
            "published_at": release.get("published_at"),
            "prerelease": bool(release.get("prerelease")),
            "draft": bool(release.get("draft")),
            "html_url": release.get("html_url"),
        },
        "head_commit": None
        if head is None
        else {
            "sha": head.get("sha"),
            "html_url": head.get("html_url"),
            "committed_at": (((head.get("commit") or {}).get("committer") or {}).get("date")),
        },
        "evaluation": evaluation,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Lidiya Open Source Radar",
        "",
        f"最後更新：`{snapshot['generated_at']}`",
        "",
        "> 本頁只提供發現、版本與候選評分；不代表核准安裝或正式部署。",
        "",
        "| 專案 | 類別 | 分數 | 建議 | 最新 Release | 最近推送 |",
        "|---|---|---:|---|---|---|",
    ]
    for item in sorted(snapshot["projects"], key=lambda row: (-row["evaluation"]["score"], row["repo"])):
        release = item.get("latest_release") or {}
        release_tag = release.get("tag") or "無正式 Release"
        pushed_at = (item.get("repository") or {}).get("pushed_at") or "未知"
        lines.append(
            f"| `{item['repo']}` | {item.get('category') or ''} | "
            f"{item['evaluation']['score']} | `{item['evaluation']['decision']}` | "
            f"{release_tag} | {pushed_at} |"
        )

    lines.extend(
        [
            "",
            "## 使用規則",
            "",
            "1. 新視窗先讀家，再讀本雷達。",
            "2. 只有 `SANDBOX_EVALUATION` 以上才值得建立測試候選。",
            "3. 安裝、模型下載、正式合併、公開發布與實體控制仍需博玄逐次解鎖。",
            "4. 所有採用必須固定版本或 commit、保存 SHA256、測試證據與回退方案。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for index, project in enumerate(registry.get("projects", [])):
        try:
            results.append(fetch_project(project))
        except Exception as exc:  # keep the remaining radar useful
            failures.append({"repo": project.get("repo", "UNKNOWN"), "error": str(exc)})
        if index:
            time.sleep(0.15)

    snapshot = {
        "schema_version": "1.0",
        "generated_at": utc_now().isoformat(),
        "source": "GitHub REST API",
        "discovery_only": True,
        "projects": results,
        "failures": failures,
    }
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    RADAR_PATH.write_text(render_markdown(snapshot), encoding="utf-8")

    print(f"updated={len(results)} failures={len(failures)}")
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
