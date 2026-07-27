"""Search keyword lists for Xiaohongshu / Nowcoder."""
from __future__ import annotations

from scripts.corpus.classify import classify_search_queries
from scripts.corpus.tech_roles import canonical_role_id, resolve_role_label

# 小红书搜索：数据开发用短词（用户口语「数开」），比牛客长 query 更贴笔记标题
_DATA_XHS_CORE: tuple[str, ...] = (
    "数开面经",
    "数开 面经",
    "数开一面",
    "数开二面",
    "数开三面",
    "数仓面经",
    "数仓 面经",
    "数仓一面",
    "数据开发面经",
    "数据开发 面经",
    "数据开发一面",
    "数据开发二面",
    "大数据开发面经",
    "大数据开发 面经",
    "大数据开发一面",
    "大数据 面经",
    "ETL面经",
    "Spark面经",
    "Hive面经",
    "Flink面经",
    "数仓开发面经",
    "离线数仓面经",
    "实时数仓面经",
    "湖仓面经",
    "数据研发面经",
    "数据平台面经",
    # ── 引擎/组件：现有语料里高频出现（Doris 139、ClickHouse 126、
    #    Kafka 388、Iceberg 69、HBase 78、Hudi 51 次）但此前无专门搜索词，
    #    补上后可定向捞到更多同类面经，而非靠泛词顺带抓 ──
    "Kafka面经",
    "ClickHouse面经",
    "Doris面经",
    "StarRocks面经",
    "Iceberg面经",
    "Hudi面经",
    "Paimon面经",
    "HBase面经",
    "湖仓一体面经",
    "数据湖面经",
    # ── SQL 与实时细分 ──
    "SQL面经",
    "HiveSQL面经",
    "SparkSQL面经",
    "FlinkSQL面经",
    "实时计算面经",
    "流计算面经",
    # ── 场景/方向：数据治理、数据质量、中台等高频主题 ──
    "数据治理面经",
    "数据质量面经",
    "数据中台面经",
    "指标平台面经",
    "数据建模面经",
    "维度建模面经",
    # ── 调度工具 ──
    "调度平台面经",
    "DolphinScheduler面经",
    "Airflow面经",
    "DataX面经",
)


def _data_xhs_keywords(companies: list[str]) -> list[str]:
    out: list[str] = list(_DATA_XHS_CORE)
    seen = set(out)
    for company in companies:
        c = company.strip()
        if not c:
            continue
        for tpl in (
            f"{c} 数开面经",
            f"{c} 数开 面经",
            f"{c} 数开一面",
            f"{c} 数据开发面经",
            f"{c} 数仓面经",
            f"{c} 大数据开发面经",
        ):
            if tpl not in seen:
                seen.add(tpl)
                out.append(tpl)
    return out


def nowcoder_queries_for_role(role_id: str, companies: list[str]) -> list[str]:
    role_label = resolve_role_label(role_id=role_id)
    return classify_search_queries(
        roles=[role_label],
        companies=companies or None,
        role_id=role_id,
    )


def xhs_keywords_for_role(role_id: str, companies: list[str]) -> list[str]:
    """Xiaohongshu search keywords (short, 面经-oriented)."""
    rid = canonical_role_id(role_id) or (role_id or "").strip()
    if rid == "data":
        return _data_xhs_keywords(companies or [])

    out: list[str] = []
    seen: set[str] = set()
    for q in nowcoder_queries_for_role(role_id, companies):
        text = q.strip()
        if not text:
            continue
        if "面经" not in text:
            text = f"{text} 面经"
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def xhs_core_keywords_for_role(role_id: str) -> list[str]:
    """Core XHS keywords without per-company expansion (faster daily sweep)."""
    rid = canonical_role_id(role_id) or (role_id or "").strip()
    if rid == "data":
        return list(_DATA_XHS_CORE)
    label = resolve_role_label(role_id=rid)
    return [f"{label} 面经", f"{label} 一面", f"{label} 二面"]


def merged_nowcoder_queries_for_roles(role_ids: list[str], companies: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for role_id in role_ids:
        for q in nowcoder_queries_for_role(role_id, companies):
            text = q.strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def merged_xhs_keywords_for_roles(role_ids: list[str], companies: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for role_id in role_ids:
        for k in xhs_keywords_for_role(role_id, companies):
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out
