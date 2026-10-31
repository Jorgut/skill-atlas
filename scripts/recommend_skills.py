#!/usr/bin/env python3
"""Recommend and orchestrate skills, models, and tools for a user request."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
AUDIT_SCRIPT = SCRIPT_DIR / "audit_skills.py"

LOADABLE_ROOTS = {
    "codex-loadable",
    "agents-loadable",
    "kimi-loadable",
    "opencode-loadable",
    "claude-loadable",
    "cc-switch",
}

CAPABILITIES = {
    "product-planning": {
        "label": "Product planning and architecture",
        "intent": ["product", "platform", "system", "architecture", "产品", "平台", "系统", "架构"],
        "skill": ["plan", "product", "architecture", "requirements", "workflow", "project"],
    },
    "frontend-ui": {
        "label": "Frontend and interface development",
        "intent": ["web", "website", "frontend", "dashboard", "interface", "react", "next.js", "网页", "网站", "前端", "界面", "仪表盘"],
        "skill": ["frontend", "react", "nextjs", "web", "ui", "sites", "shadcn"],
    },
    "design-ux": {
        "label": "Product design and UX",
        "intent": ["design", "ux", "ui", "prototype", "figma", "设计", "交互", "原型", "体验", "界面"],
        "skill": ["ux", "ui", "design", "figma", "frontend", "brand"],
    },
    "design-validation": {
        "label": "UX and design validation",
        "intent": ["ux", "ui", "hmi", "prototype", "design", "体验", "界面", "设计", "交互", "人机界面"],
        "skill": ["ux", "audit", "usability", "accessibility", "review", "validation"],
    },
    "hmi-design": {
        "label": "HMI and embedded interface design",
        "intent": ["hmi", "human machine interface", "automotive ui", "cockpit", "仪表盘", "车机", "座舱", "人机界面"],
        "skill": ["hmi", "ux", "ui", "design", "figma", "frontend"],
    },
    "backend-api": {
        "label": "Backend and API development",
        "intent": ["api", "backend", "server", "account", "upload", "sync", "后端", "服务端", "接口", "账户", "上传", "同步"],
        "skill": ["backend", "api", "server", "django", "springboot", "golang"],
    },
    "database-storage": {
        "label": "Database and storage",
        "intent": ["database", "postgres", "postgresql", "data", "storage", "upload", "history", "数据库", "数据", "存储", "上传", "历史记录"],
        "skill": ["database", "postgres", "supabase", "storage", "clickhouse", "data"],
    },
    "auth-security": {
        "label": "Authentication and security",
        "intent": ["auth", "authentication", "login", "account", "permission", "private", "登录", "账户", "权限", "隐私", "安全"],
        "skill": ["auth", "security", "permission", "sign-in", "oauth"],
    },
    "ai-ml": {
        "label": "AI and model integration",
        "intent": ["ai", "llm", "model", "generate", "agent", "人工智能", "大模型", "模型", "生成", "智能体"],
        "skill": ["ai", "llm", "model", "hugging", "transformers"],
    },
    "documents-presentations": {
        "label": "Documents and presentations",
        "intent": ["document", "pdf", "ppt", "pptx", "slide", "presentation", "文档", "演示", "幻灯片", "导出"],
        "skill": ["pdf", "ppt", "pptx", "slide", "slides", "presentation", "docx", "document", "documents"],
    },
    "browser-testing": {
        "label": "Browser automation and testing",
        "intent": ["web", "website", "browser", "e2e", "test", "网页", "网站", "浏览器", "测试", "自动化"],
        "skill": ["playwright", "browser", "testing", "e2e", "verification"],
    },
    "quality-testing": {
        "label": "Testing and quality verification",
        "intent": ["test", "quality", "verify", "reliable", "测试", "质量", "验证", "可靠"],
        "skill": ["testing", "test", "tdd", "verification", "review", "eval"],
    },
    "deployment-ops": {
        "label": "Deployment and operations",
        "intent": ["deploy", "deployment", "hosting", "production", "cloud", "上线", "部署", "托管", "云"],
        "skill": ["deploy", "deployment", "vercel", "hosting", "cicd", "observability"],
    },
    "payments": {
        "label": "Payments and billing",
        "intent": ["payment", "billing", "subscription", "checkout", "付费", "支付", "订阅", "账单"],
        "skill": ["payment", "payments", "stripe", "billing"],
    },
    "media": {
        "label": "Image, audio, and video workflows",
        "intent": ["image", "video", "audio", "media", "图片", "图像", "视频", "音频", "媒体"],
        "skill": ["image", "video", "audio", "media", "remotion", "youtube"],
    },
    "animation-motion": {
        "label": "Animation and motion production",
        "intent": ["animation", "animate", "motion", "animated", "动画", "动效", "运动设计"],
        "skill": ["animation", "animated", "motion", "remotion", "video", "gif"],
    },
    "model-selection": {
        "label": "AI model research and selection",
        "intent": ["best model", "which model", "model comparison", "benchmark", "模型更好", "什么模型", "哪个模型", "模型选择", "模型对比"],
        "skill": ["model", "hugging", "evaluation", "eval", "benchmark", "search"],
    },
    "architecture-interior": {
        "label": "Architecture and interior design",
        "intent": ["architecture", "architect", "interior", "building", "space planning", "spatial design", "建筑", "建筑师", "室内", "室内设计", "空间设计", "空间规划", "软装"],
        "skill": ["architecture", "architect", "interior", "space", "arch", "archviz", "boq", "spatial"],
    },
    "cad-3d-modeling": {
        "label": "CAD and 3D modeling automation",
        "intent": ["3d", "cad", "bim", "rhino", "grasshopper", "blender", "sketchup", "revit", "autocad", "freecad", "modeling", "建模", "犀牛", "草蜢"],
        "skill": ["3d", "cad", "bim", "rhino", "grasshopper", "blender", "sketchup", "revit", "autocad", "freecad", "modeling"],
    },
}

DEFAULT_CAPABILITIES = ["product-planning"]

RESEARCH_MODES = ("quick", "balanced", "benchmark")

ROLE_ORDER = (
    "research",
    "design",
    "discovery",
    "planning",
    "implementation",
    "review",
    "verification",
)

COMPARISON_RUBRIC = [
    {"criterion": "task-fit", "weight": 30, "evidence": "Trigger precision and direct coverage of the requested capability."},
    {"criterion": "workflow-quality", "weight": 20, "evidence": "Procedural depth, examples, scripts, references, and output quality."},
    {"criterion": "evals", "weight": 15, "evidence": "Executable tests, eval cases, regression coverage, and reproducible evidence."},
    {"criterion": "maintenance", "weight": 10, "evidence": "Recent releases, issue activity, compatibility notes, and maintained dependencies."},
    {"criterion": "source-license", "weight": 10, "evidence": "Inspectable source, attributable author, repository history, and usable license."},
    {"criterion": "compatibility", "weight": 10, "evidence": "Codex, OpenCode, Claude Code, dependency, and platform fit."},
    {"criterion": "safety", "weight": 5, "evidence": "Static review, permissions, install behavior, and absence of hidden destructive actions."},
]

QUERY_TRANSLATIONS = {
    "人工智能": "ai",
    "大模型": "llm",
    "智能体": "agent",
    "生成": "generation",
    "网页": "web",
    "网站": "website",
    "前端": "frontend",
    "界面": "ui",
    "设计": "design",
    "交互": "ux",
    "后端": "backend",
    "接口": "api",
    "数据库": "database",
    "存储": "storage",
    "登录": "authentication",
    "权限": "authorization",
    "文档": "document",
    "演示": "presentation",
    "幻灯片": "slides",
    "导出": "export",
    "测试": "testing",
    "部署": "deployment",
    "上线": "deployment",
    "支付": "payments",
    "订阅": "subscription",
    "图片": "image",
    "图像": "image",
    "视频": "video",
    "音频": "audio",
    "动画": "animation",
    "动效": "motion",
    "车机": "automotive hmi",
    "座舱": "cockpit hmi",
    "人机界面": "hmi",
    "建筑": "architecture",
    "室内": "interior",
    "建模": "3d modeling",
    "犀牛": "rhino",
    "草蜢": "grasshopper",
}

STACK_HINTS = {
    "django": ["django"],
    "springboot": ["springboot", "spring boot"],
    "golang": ["golang", "go language"],
    "cpp": ["cpp", "c++"],
    "java": ["java"],
    "python": ["python"],
}

SPECIALIZED_SKILL_HINTS = {
    "slack-gif-creator": ["slack", "gif"],
    "hatch-pet": ["pet", "mascot", "sprite", "宠物", "吉祥物", "精灵图"],
}

PRESENTATION_GENERATORS = {
    "slides",
    "frontend-slides",
    "presentations",
    "pptx",
    "ppt-agent",
    "ppt-agent-skill",
    "guizang-ppt-skill",
    "powerpoint",
    "canva",
}

# Discovery and management skills can route work, but they do not perform the
# product-domain capability they mention in their own descriptions.
META_SKILLS = {
    "search-skill",
    "skill-atlas",
    "skill-installer",
    "skill-manager",
    "skill-update-auditor",
}


def run_audit(roots: list[str]) -> list[dict[str, Any]]:
    cmd = [sys.executable, str(AUDIT_SCRIPT), "--format", "json"]
    for root in roots:
        cmd.extend(["--root", root])
    output = subprocess.check_output(cmd, text=True)
    return json.loads(output)


def contains_term(text: str, term: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", term):
        return term in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def product_tokens(product: str) -> list[str]:
    english = re.findall(r"[a-z0-9][a-z0-9.+_-]{1,}", product.lower())
    stop = {"product", "build", "create", "develop", "support", "using", "and", "for", "find", "select", "current", "开发", "产品", "一个", "支持", "可以", "用户"}
    result: list[str] = []
    translated = [translation for source, translation in QUERY_TRANSLATIONS.items() if source in product]
    for term in english + translated:
        term = term.strip("._+-")
        if len(term) < 2 or term in stop or term in result:
            continue
        result.append(term)
    return result[:12]


def detect_capabilities(product: str) -> list[str]:
    text = product.lower()
    detected = []
    for key, definition in CAPABILITIES.items():
        if any(contains_term(text, term) for term in definition["intent"]):
            detected.append(key)
    for key in DEFAULT_CAPABILITIES:
        if key not in detected:
            detected.append(key)
    if any(key in detected for key in ["database-storage", "auth-security", "payments"]):
        if "backend-api" not in detected:
            detected.insert(0, "backend-api")
    return detected


def research_targets(request: str, capabilities: list[str]) -> list[dict[str, Any]]:
    text = request.lower()
    terms = product_tokens(request)
    targets: list[dict[str, Any]] = []

    if "model-selection" in capabilities:
        domain = "animation" if "animation-motion" in capabilities else " ".join(terms[:4])
        targets.append(
            {
                "type": "model",
                "subject": f"current AI models for {domain}".strip(),
                "reason": "Model quality changes faster than installed skill metadata; compare current benchmarks, licensing, cost, latency, controllability, and deployment constraints.",
                "queries": [
                    f"best current AI models for {domain} benchmark comparison",
                    f"{domain} AI model leaderboard license API pricing",
                ],
            }
        )

    modeling_tools = [name for name in ["rhino", "grasshopper", "blender", "sketchup"] if contains_term(text, name)]
    if "cad-3d-modeling" in capabilities:
        tools = modeling_tools or ["rhino", "blender", "sketchup"]
        targets.append(
            {
                "type": "software-integration",
                "subject": ", ".join(tools),
                "reason": "A skill can provide workflow knowledge, but actual automation may also require an installed application, CLI, Python API, plugin, or MCP connector.",
                "queries": [
                    f"{' '.join(tools)} AI agent skill MCP automation GitHub",
                    f"{' '.join(tools)} scripting API agent workflow SKILL.md",
                ],
            }
        )

    if "hmi-design" in capabilities:
        targets.append(
            {
                "type": "domain-reference",
                "subject": "HMI design standards and validation",
                "reason": "General UI skills should be checked against domain constraints such as glanceability, safety, hardware states, input methods, and accessibility.",
                "queries": [
                    "HMI UX design skill automotive cockpit UI validation SKILL.md",
                    "HMI design guidelines usability safety interaction benchmark",
                ],
            }
        )
    component_terms = (
        "component",
        "library",
        "design system",
        "ui kit",
        "liquid glass",
        "组件",
        "组件库",
        "设计系统",
    )
    if (
        any(key in capabilities for key in ("frontend-ui", "design-ux", "hmi-design"))
        and any(contains_term(text, term) for term in component_terms)
    ):
        subject = " ".join(terms[:4]) or "interface design"
        targets.append(
            {
                "type": "component-library",
                "subject": subject,
                "reason": "A component library supplies executable UI primitives; compare framework compatibility, accessibility, bundle cost, maintenance, license, and design fit separately from Agent skills.",
                "queries": [
                    f"best maintained {subject} React component library accessibility",
                    f"{subject} UI component library GitHub npm license bundle size",
                ],
            }
        )
    return targets


def unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record.get("name", "")].append(record)
    result = []
    for name, items in grouped.items():
        preferred = sorted(
            items,
            key=lambda item: (
                item.get("root_class") not in LOADABLE_ROOTS,
                item.get("maintenance_class") == "tool-bundled/cache",
                item.get("path", ""),
            ),
        )[0]
        result.append({**preferred, "name": name, "copies": len(items)})
    return result


def stack_matches_product(record: dict[str, Any], product: str) -> bool:
    name = record.get("name", "").lower()
    text = product.lower()
    if name == "youtube-clipper":
        return any(
            contains_term(text, term)
            for term in ("youtube", "youtube clip", "video clip", "video editing", "剪辑", "切片", "字幕")
        )
    if "remotion" in name:
        if contains_term(text, "remotion"):
            return True
        has_video = any(contains_term(text, term) for term in ("video", "视频"))
        has_production = any(
            contains_term(text, term)
            for term in ("create video", "generate video", "render video", "video production", "制作视频", "生成视频", "渲染视频")
        )
        return has_video and has_production
    required_terms = SPECIALIZED_SKILL_HINTS.get(name)
    if required_terms and not any(contains_term(text, term) for term in required_terms):
        return False
    for stack, aliases in STACK_HINTS.items():
        if stack not in name:
            continue
        return any(contains_term(product.lower(), alias) for alias in aliases)
    return True


def generator_family(name: str) -> str | None:
    return "presentation-primary" if name.lower() in PRESENTATION_GENERATORS else None


def select_exclusive_generators(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        family = generator_family(item["skill"])
        if family:
            grouped[family].append(item)

    selected_names: set[str] = set()
    notes = []
    for family, candidates in grouped.items():
        ordered = sorted(
            candidates,
            key=lambda item: (
                item["capability"] != "documents-presentations",
                -item["score"],
                item["skill"],
            ),
        )
        selected_names.add(ordered[0]["skill"])
        alternatives = list(dict.fromkeys(item["skill"] for item in ordered[1:]))
        if alternatives:
            notes.append(
                {
                    "family": family,
                    "selected": ordered[0]["skill"],
                    "alternatives": alternatives,
                    "reason": "Overlapping generators are alternatives, not simultaneous primaries.",
                }
            )

    filtered = [
        item
        for item in items
        if generator_family(item["skill"]) is None or item["skill"] in selected_names
    ]
    return filtered, notes


def score_record(
    record: dict[str, Any], capability: str, product: str, product_terms: list[str]
) -> tuple[int, list[str]]:
    if record.get("name", "").lower() in META_SKILLS:
        return 0, []
    if not stack_matches_product(record, product):
        return 0, []
    name = record.get("name", "").lower()
    text = f"{record.get('name', '')} {record.get('description', '')}".lower()
    matched = [term for term in CAPABILITIES[capability]["skill"] if contains_term(text, term)]
    name_matches = [term for term in matched if contains_term(name, term)]
    name_match = bool(name_matches)
    if len(matched) < 2 and not name_match:
        return 0, []
    product_matches = [term for term in product_terms if contains_term(text, term.lower())]
    reasons = list(dict.fromkeys(matched + product_matches))
    return len(matched) * 3 + len(name_matches) * 5 + len(product_matches), reasons


def search_queries(capability: str, product_terms: list[str]) -> list[str]:
    definition = CAPABILITIES[capability]
    context = " ".join(product_terms[:4])
    subject = f"{context} {definition['label']}".strip()
    return [
        f'{subject} agent skill "SKILL.md" GitHub',
        f'{subject} Claude Code skill',
        f'{subject} Codex skill',
        f'{subject} OpenCode skill',
    ]


def comparison_queries(
    capability: str, product_terms: list[str], mode: str
) -> list[str]:
    queries = search_queries(capability, product_terms)
    definition = CAPABILITIES[capability]
    context = " ".join(product_terms[:4])
    subject = f"{context} {definition['label']}".strip()
    queries.extend(
        [
            f'{subject} site:skills.sh "SKILL.md"',
            f'{subject} awesome agent skills GitHub',
        ]
    )
    if mode == "benchmark":
        queries.extend(
            [
                f'{subject} agent skill eval benchmark',
                f'{subject} SkillsMP SkillMD Playbooks ClawHub security license maintenance',
            ]
        )
    return queries


def build_comparison_plan(
    mode: str,
    capabilities: list[str],
    product_terms: list[str],
    ready: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if mode == "quick":
        return []
    local_by_capability: dict[str, list[str]] = defaultdict(list)
    for item in ready:
        local_by_capability[item["capability"]].append(item["skill"])
    return [
        {
            "capability": capability,
            "capability_label": CAPABILITIES[capability]["label"],
            "local_candidates": local_by_capability.get(capability, []),
            "queries": comparison_queries(capability, product_terms, mode),
            "candidate_target": 8 if mode == "benchmark" else 3,
            "required_source_types": [
                "marketplace",
                "official-or-github",
                "community",
            ],
            "required_checks": [
                "source and author",
                "license",
                "maintenance activity",
                "platform compatibility",
                "eval and test evidence",
                "strict security review",
            ],
        }
        for capability in capabilities
    ]


PHASE_CAPABILITIES = {
    "research": ["model-selection", "product-planning"],
    "design": ["hmi-design", "architecture-interior", "design-ux"],
    "production": [
        "animation-motion",
        "cad-3d-modeling",
        "media",
        "frontend-ui",
        "backend-api",
        "documents-presentations",
    ],
    "verification": ["design-validation", "quality-testing", "browser-testing", "auth-security"],
}


def build_orchestration(use_now: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_capability: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in use_now:
        by_capability[item["capability"]].append(item)

    used: set[str] = set()
    phases = []
    for phase, capabilities in PHASE_CAPABILITIES.items():
        selections = []
        for capability in capabilities:
            candidates = by_capability.get(capability, [])
            primary = next((item for item in candidates if item["skill"] not in used), None)
            if not primary:
                continue
            used.add(primary["skill"])
            selections.append(
                {
                    "skill": primary["skill"],
                    "capability": capability,
                    "capability_label": primary["capability_label"],
                    "role": (
                        "primary"
                        if phase in {"design", "production"} and not selections
                        else "reviewer"
                        if phase in {"design", "verification"}
                        else "support"
                    ),
                    "path": primary["path"],
                }
            )
        if selections:
            phases.append({"phase": phase, "skills": selections})
    return phases


def build_local_artifact_orchestration(
    skill_phases: list[dict[str, Any]],
    component_libraries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    plan = []
    for phase in skill_phases:
        for skill in phase["skills"]:
            plan.append(
                {
                    "stage": phase["phase"],
                    "role": skill["role"],
                    "artifact_type": "skill",
                    "artifact": skill["skill"],
                    "availability": "installed",
                    "path": skill["path"],
                }
            )
    for library in component_libraries:
        plan.append(
            {
                "stage": "production",
                "role": "implementation",
                "artifact_type": "component-library",
                "artifact": library["name"],
                "availability": library["availability"],
                "path": library["repository_path"],
            }
        )
    stage_order = {"research": 0, "design": 1, "production": 2, "verification": 3}
    return sorted(plan, key=lambda item: stage_order[item["stage"]])


def match_market_candidates(
    product: str,
    capabilities: list[str],
    candidates: list[dict[str, Any]],
    installed_names: set[str],
    market_fresh: bool,
) -> list[dict[str, Any]]:
    text = product.lower()
    matches = []
    for candidate in candidates:
        matched_capabilities = [
            capability
            for capability in candidate.get("capabilities", [])
            if capability in capabilities
        ]
        if not matched_capabilities:
            continue
        keywords = candidate.get("keywords", [])
        if keywords and not any(contains_term(text, keyword.lower()) for keyword in keywords):
            continue
        artifact_type = candidate.get("artifact_type", "skill")
        installed = artifact_type == "skill" and candidate.get("name", "") in installed_names
        availability = {
            "component-library": "dependency-required",
            "model": "selection-required",
            "software-integration": "integration-required",
            "domain-reference": "reference-required",
        }.get(artifact_type, "installed" if installed else "install-required")
        matches.append(
            {
                "name": candidate.get("name", ""),
                "artifact_type": artifact_type,
                "url": candidate.get("url", ""),
                "capabilities": matched_capabilities,
                "roles": candidate.get("roles", []),
                "platforms": candidate.get("platforms", []),
                "score": candidate.get("score"),
                "availability": availability,
                "review_status": "current" if market_fresh else "refresh-required",
            }
        )
    if any(item["score"] is not None for item in matches):
        matches.sort(
            key=lambda item: (
                item["score"] is None,
                -(item["score"] or 0),
                item["name"],
            )
        )
    return matches


def build_reviewed_orchestration(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    family_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in matches:
        family = candidate.get("generator_family") or generator_family(candidate["name"])
        if family:
            family_candidates[family].append(candidate)
    family_winners = {
        family: sorted(
            candidates,
            key=lambda item: (item["score"] is None, -(item["score"] or 0), item["name"]),
        )[0]["name"]
        for family, candidates in family_candidates.items()
    }
    family_alternatives = {
        winner: [item["name"] for item in candidates if item["name"] != winner]
        for family, candidates in family_candidates.items()
        for winner in [family_winners[family]]
    }

    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in matches:
        family = candidate.get("generator_family") or generator_family(candidate["name"])
        if family and family_winners[family] != candidate["name"]:
            continue
        for role in candidate["roles"]:
            by_role[role].append(candidate)

    plan = []
    used: set[str] = set()
    for role in ROLE_ORDER:
        candidates = [item for item in by_role[role] if item["name"] not in used]
        if not candidates:
            continue
        selected = candidates[0]
        used.add(selected["name"])
        plan.append(
            {
                "role": role,
                "artifact": selected["name"],
                "artifact_type": selected["artifact_type"],
                "skill": selected["name"],
                "url": selected["url"],
                "availability": selected["availability"],
                "review_status": selected["review_status"],
                "alternatives": list(dict.fromkeys(
                    [item["name"] for item in candidates[1:]]
                    + family_alternatives.get(selected["name"], [])
                )),
            }
        )
    return plan


def build_recommendation(
    product: str,
    records: list[dict[str, Any]],
    limit: int,
    research_mode: str = "balanced",
) -> dict[str, Any]:
    if research_mode not in RESEARCH_MODES:
        raise ValueError(f"Unsupported research mode: {research_mode}")
    capabilities = detect_capabilities(product)
    terms = product_tokens(product)
    local = unique_records(records)
    ready: list[dict[str, Any]] = []
    managed: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for capability in capabilities:
        matches = []
        for record in local:
            score, reasons = score_record(record, capability, product, terms)
            if score:
                matches.append((score, record, reasons))
        matches.sort(key=lambda item: (-item[0], item[1].get("name", "")))

        loadable = [item for item in matches if item[1].get("root_class") in LOADABLE_ROOTS][:limit]
        platform_managed = [
            item for item in matches if item[1].get("root_class") not in LOADABLE_ROOTS
        ][:limit]
        target = ready if loadable else managed
        source = loadable if loadable else platform_managed
        for score, record, reasons in source:
            target.append(
                {
                    "capability": capability,
                    "capability_label": CAPABILITIES[capability]["label"],
                    "skill": record.get("name", ""),
                    "description": record.get("description", ""),
                    "path": record.get("path", ""),
                    "root_class": record.get("root_class", ""),
                    "maintenance_class": record.get("maintenance_class", ""),
                    "score": score,
                    "matched_terms": reasons,
                }
            )
        if not loadable:
            gaps.append(
                {
                    "capability": capability,
                    "capability_label": CAPABILITIES[capability]["label"],
                    "queries": search_queries(capability, terms),
                    "local_platform_match": bool(platform_managed),
                }
            )

    ready, generator_alternatives = select_exclusive_generators(ready)
    orchestration = build_orchestration(ready)
    comparison_plan = build_comparison_plan(research_mode, capabilities, terms, ready)
    external_required = bool(gaps or comparison_plan)
    return {
        "product": product,
        "research_mode": research_mode,
        "recommendation_status": "provisional" if external_required else "local-complete",
        "detected_capabilities": [
            {"id": key, "label": CAPABILITIES[key]["label"]} for key in capabilities
        ],
        "use_now": ready,
        "generator_alternatives": generator_alternatives,
        "orchestration": orchestration,
        "platform_managed_matches": managed,
        "external_search_gaps": gaps,
        "external_comparison_plan": comparison_plan,
        "comparison_rubric": COMPARISON_RUBRIC,
        "external_research_targets": research_targets(product, capabilities),
        "policy": {
            "automatic_install": False,
            "external_candidates_require": [
                "inspectable source",
                "license review",
                "maintenance review",
                "strict static security review",
                "explicit user confirmation",
            ],
        },
    }


def emit_markdown(result: dict[str, Any], include_orchestration: bool) -> None:
    print("# Product Skill Recommendation")
    print()
    print(f"- Request: {result['product']}")
    print(f"- Research mode: {result['research_mode']}")
    print(f"- Recommendation status: {result['recommendation_status']}")
    print()

    if result.get("market_freshness"):
        freshness = result["market_freshness"]
        print("## Public Market Freshness")
        print()
        print(f"- Status: {freshness['status']}")
        print(f"- Researched at: {freshness['researched_at'] or 'never'}")
        print(f"- Age hours: {freshness['age_hours'] if freshness['age_hours'] is not None else 'unknown'}")
        print(f"- TTL hours: {freshness['ttl_hours']}")
        print(f"- Refresh required: {str(result['market_refresh_required']).lower()}")
        if result["market_refresh_required"]:
            print("- Next step: execute the external comparison plan and save reviewed results with `skill-atlas market refresh --results FILE`.")
        print()

    if result.get("reviewed_market_matches"):
        print("## Reviewed Market Matches")
        print()
        for item in result["reviewed_market_matches"]:
            roles = ", ".join(item["roles"]) or "unassigned"
            print(f"- {item['name']} ({item['artifact_type']}; {item['availability']}; review: {item['review_status']}; roles: {roles})")
            print(f"  - source: {item['url']}")
        print()

    if result["external_comparison_plan"]:
        print("## External Benchmark Plan")
        print()
        print("Local matches are provisional until these external candidates are researched and scored with the same rubric.")
        print()
        for item in result["external_comparison_plan"]:
            local = ", ".join(item["local_candidates"]) or "none"
            print(f"- {item['capability_label']} (local: {local}; target: {item['candidate_target']} external candidates)")
            for query in item["queries"]:
                print(f"  - `{query}`")
        print()

        print("## Comparison Rubric")
        print()
        for criterion in result["comparison_rubric"]:
            print(f"- {criterion['criterion']}: {criterion['weight']} points")
            print(f"  - evidence: {criterion['evidence']}")
        print()

    if result.get("generator_alternatives"):
        print("## Generator Alternatives")
        print()
        for item in result["generator_alternatives"]:
            alternatives = ", ".join(item["alternatives"])
            print(f"- {item['selected']} is the primary for `{item['family']}`")
            print(f"  - alternatives: {alternatives}")
            print(f"  - reason: {item['reason']}")
        print()

    if result.get("local_component_libraries"):
        print("## Local Component Libraries")
        print()
        for item in result["local_component_libraries"]:
            capabilities = ", ".join(item["matched_capabilities"])
            print(f"- {item['name']} ({item['version']}; {item['availability']})")
            print(f"  - capabilities: {capabilities}")
            print(f"  - manifest: `{item['manifest_path']}`")
        print()

    print("## Required Capabilities")
    print()
    for capability in result["detected_capabilities"]:
        print(f"- {capability['label']} (`{capability['id']}`)")
    print()

    print("## Use Now")
    print()
    if not result["use_now"]:
        print("- No directly loadable local matches were found.")
    for item in result["use_now"]:
        print(f"- {item['skill']} -> {item['capability_label']}")
        print(f"  - path: `{item['path']}`")
        print(f"  - matched: {', '.join(item['matched_terms'])}")
    print()

    if include_orchestration:
        print("## Suggested Orchestration")
        print()
        if not result["orchestration"]:
            print("- No local multi-skill workflow could be assembled. Use the external gaps below.")
        for phase in result["orchestration"]:
            names = " -> ".join(item["skill"] for item in phase["skills"])
            print(f"- {phase['phase']}: {names}")
            for item in phase["skills"]:
                print(f"  - {item['skill']}: {item['role']} for {item['capability_label']}")
        print()

        if result.get("artifact_orchestration"):
            print("## Local Artifact Plan")
            print()
            for item in result["artifact_orchestration"]:
                print(
                    f"- {item['stage']}: {item['artifact']} "
                    f"({item['artifact_type']}; {item['role']}; {item['availability']})"
                )
            print()

        if result.get("reviewed_orchestration"):
            print("## Reviewed Cross-Skill Plan")
            print()
            print("This plan may include external candidates. Install-required entries need confirmation; refresh-required entries need current research before selection.")
            print()
            for item in result["reviewed_orchestration"]:
                alternatives = ", ".join(item["alternatives"]) or "none"
                print(f"- {item['role']}: {item['skill']} ({item['availability']}; review: {item['review_status']})")
                print(f"  - alternatives: {alternatives}")
            print()

    if result["platform_managed_matches"]:
        print("## Platform-Managed Matches")
        print()
        print("These matches exist in a tool-managed or non-loadable location. Verify platform availability; do not edit cache copies in place.")
        print()
        for item in result["platform_managed_matches"]:
            print(f"- {item['skill']} -> {item['capability_label']} (`{item['root_class']}`)")
            print(f"  - path: `{item['path']}`")
        print()

    print("## External Search Gaps")
    print()
    if not result["external_search_gaps"]:
        print("- No capability gaps were detected from the local inventory.")
    for gap in result["external_search_gaps"]:
        note = "local platform-managed match exists" if gap["local_platform_match"] else "no local match"
        print(f"- {gap['capability_label']} ({note})")
        for query in gap["queries"]:
            print(f"  - `{query}`")
    print()

    if result["external_research_targets"]:
        print("## Models, Tools, and Domain Research")
        print()
        for target in result["external_research_targets"]:
            print(f"- {target['subject']} (`{target['type']}`)")
            print(f"  - why: {target['reason']}")
            for query in target["queries"]:
                print(f"  - `{query}`")
        print()

    print("## Safety Gate")
    print()
    print("External results are candidates only. Do not install automatically; verify source, license, maintenance, static security findings, and obtain explicit confirmation first.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    request_group = parser.add_mutually_exclusive_group(required=True)
    request_group.add_argument("--request", help="Describe the task, product, model question, or tool workflow.")
    request_group.add_argument("--product", help="Compatibility alias for --request.")
    parser.add_argument("--root", action="append", default=[], help="Skill root to scan. May be repeated.")
    parser.add_argument("--mode", choices=["recommend", "orchestrate"], default="orchestrate")
    parser.add_argument("--research-mode", choices=RESEARCH_MODES, default="balanced")
    parser.add_argument("--limit-per-capability", type=int, default=2)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = args.request or args.product
    result = build_recommendation(
        request,
        run_audit(args.root),
        max(1, args.limit_per_capability),
        args.research_mode,
    )
    if args.mode == "recommend":
        result = {key: value for key, value in result.items() if key != "orchestration"}
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_markdown(result, args.mode == "orchestrate")


if __name__ == "__main__":
    main()
