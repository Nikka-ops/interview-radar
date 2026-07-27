"""Preset technical job roles for search and UI selection."""
from __future__ import annotations

from dataclasses import dataclass

# 历史 role_id 归并（Agent 开发已并入 ai_app）
ROLE_ID_ALIASES: dict[str, str] = {
    "agent": "ai_app",
}


@dataclass(frozen=True)
class TechRole:
    id: str
    label: str
    search_as: str
    category: str = "技术岗"
    keywords: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "search_as": self.search_as,
            "category": self.category,
            "keywords": list(self.keywords),
        }


TECH_ROLES: tuple[TechRole, ...] = (
    TechRole("backend", "后端开发", "后端开发", keywords=("Java", "Go", "微服务")),
    TechRole("frontend", "前端开发", "前端开发", keywords=("React", "Vue", "前端")),
    TechRole("algorithm", "算法工程师", "算法工程师", keywords=("机器学习", "深度学习", "CV", "NLP")),
    TechRole("llm", "大模型", "大模型", keywords=("LLM", "预训练", "SFT", "RLHF")),
    TechRole(
        "ai_app",
        "Agent 开发",
        "Agent 开发",
        keywords=("RAG", "LangChain", "Agent", "MCP", "应用", "工具调用", "AI应用", "智能体"),
    ),
    TechRole(
        "data",
        "数据开发",
        "数据开发",
        keywords=(
            "数开",
            "Spark",
            "Hive",
            "Flink",
            "ETL",
            "数仓",
            "数据仓库",
            "离线数仓",
            "实时数仓",
            "湖仓",
            "大数据开发",
            "数据平台",
            "数据开发工程师",
            "数仓工程师",
            "ODS",
            "DWD",
            # 引擎/组件：数据开发面经的高频判定信号
            "Kafka",
            "ClickHouse",
            "Doris",
            "StarRocks",
            "Iceberg",
            "Hudi",
            "Paimon",
            "HBase",
            "数据湖",
            "湖仓一体",
            # 场景/工具
            "数据治理",
            "数据质量",
            "数据中台",
            "维度建模",
            "DolphinScheduler",
            "DataX",
        ),
    ),
    TechRole("data_analyst", "数据分析", "数据分析", keywords=("SQL", "指标", "BI")),
    TechRole("qa", "测试开发", "测试开发", keywords=("自动化测试", "QA", "测开")),
    TechRole("product", "产品", "产品", keywords=("产品经理", "产品岗", "商业产品")),
    TechRole("client", "客户端开发", "客户端开发", keywords=("Android", "iOS", "Flutter")),
    TechRole("infra", "基础架构", "基础架构", keywords=("K8s", "SRE", "运维")),
    TechRole("security", "安全工程师", "安全工程师", keywords=("渗透", "安全")),
)

DEFAULT_ROLE_ID = "data"


def _label_to_id() -> dict[str, str]:
    out: dict[str, str] = {}
    for r in TECH_ROLES:
        out[r.label] = r.id
        out[r.search_as] = r.id
    return out


def canonical_role_id(role_id: str | None) -> str:
    rid = (role_id or "").strip()
    if not rid:
        return ""
    rid = ROLE_ID_ALIASES.get(rid, rid)
    # Chinese labels ("数据开发") must resolve to their role id ("data") so
    # comparisons against AI-returned ids work.
    return _label_to_id().get(rid, rid)


def equivalent_role_ids(role_id: str | None) -> list[str]:
    """同一合并岗位下的历史 role_id（用于合并缓存题库）。"""
    canonical = canonical_role_id(role_id) or (role_id or "").strip()
    if canonical == "ai_app":
        return ["ai_app", "agent"]
    if canonical:
        return [canonical]
    return []


def list_tech_roles() -> list[dict]:
    return [r.to_dict() for r in TECH_ROLES]


def list_focus_tech_roles() -> list[dict]:
    from scripts.config import focus_role_ids

    allowed = set(focus_role_ids())
    return [r.to_dict() for r in TECH_ROLES if r.id in allowed]


def get_tech_role(role_id: str) -> TechRole | None:
    rid = canonical_role_id(role_id)
    if not rid:
        return None
    for role in TECH_ROLES:
        if role.id == rid:
            return role
    return None


def resolve_role_label(role_id: str | None = None, role_text: str | None = None) -> str:
    if role_id:
        found = get_tech_role(role_id)
        if found:
            return found.search_as
    text = (role_text or "").strip()
    if text:
        return text
    default = get_tech_role(DEFAULT_ROLE_ID)
    return default.search_as if default else "数据开发"


def parse_role_ids(role_id: str = "", role_ids: str = "") -> list[str]:
    """Parse --role-id / --role-ids / env into deduped canonical role_id list."""
    if role_ids.strip():
        out: list[str] = []
        seen: set[str] = set()
        for raw in role_ids.replace(";", ",").split(","):
            rid = canonical_role_id(raw.strip())
            if rid and rid not in seen:
                seen.add(rid)
                out.append(rid)
        if out:
            return out
    if (role_id or "").strip():
        return [canonical_role_id(role_id.strip())]
    from scripts.config import focus_role_ids

    return focus_role_ids()
