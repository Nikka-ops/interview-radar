"""DeepSeek agent: post gate, question cluster/answers. Rules only when no API key."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from scripts.config import (
    cache_dir,
    deepseek_api_base,
    deepseek_api_key,
    deepseek_model,
    deepseek_use_proxy,
    post_ai_filter_enabled,
    post_ai_filter_max_chars,
)
from scripts.corpus.dedupe_rank import _max_date, _union, dedupe_and_rank
from scripts.corpus.semantic_merge import merge_similar_questions
from scripts.corpus.tech_roles import canonical_role_id
from scripts.models import Question

_POST_SYS = (
    "判断是否真实技术岗面试面经（本人复盘：题目/流程/手撕/凉经）。"
    "keep=false：广告、培训、求助、外贸/海关/营销、学习路线、非技术面试、后端/Java/Go/测开/前端/产品/运营。"
    "keep=true→role_id:data|ai_app|null；topics:涉及的考察方向列表，从[Spark/计算,Hive/SQL,数仓建模,Flink/实时,数据工程,RAG,Agent,MCP/协议,LLM基础,手撕代码,项目深挖,后端八股,产品/业务,综合]中选，可多选。"
    'JSON:{"keep":bool,"role_id":str|null,"topics":list[str],"reason":str}'
)
_CLUSTER_SYS = (
    "整理数据开发/AI应用面试题库。输入 [{id,text}]。"
    "合并相似题为 groups(canonical,topic,ids)；canonical 必须是一道具体的题目问句，"
    "禁止用类别名（如'后端八股'/'项目深挖'）概括；仅合并考察点相同的题，不同题不得并组；"
    "drop：自我介绍/薪资/反问/寒暄/废话/感慨吐槽/求职经验叙述/非问句段落，"
    "以及明显属于后端Java/Go/C++系统编程的题目（如shared_ptr/JVM/Spring/线程池/HTTP框架等纯后端题）。"
    "topic 从[Spark/计算,Hive/SQL,数仓建模,Flink/实时,数据工程,RAG,Agent,MCP/协议,LLM基础,手撕代码,项目深挖,后端八股,产品/业务,综合]选。"
    'JSON:{"groups":[{"canonical":str,"topic":str,"ids":[str]}],"drop":[str]}'
)
_ANSWER_SYS = (
    "写数据开发/Agent 面试题简明参考答案，要点式 120～280 字。"
    '输入 {"role":str,"items":[{"id":str,"text":str,"topic":str}]}→{"answers":[{"id":str,"answer":str}]}'
)
_TOPIC_LABELS = {
    "Spark/计算", "Hive/SQL", "数仓建模", "Flink/实时", "数据工程", "RAG", "Agent",
    "MCP/协议", "LLM基础", "手撕代码", "项目深挖", "后端八股", "产品/业务", "综合",
    "AI应用与集成", "数据库与缓存", "系统设计", "设计题",
}
_OFFLINE_POST = re.compile(r"面经|凉经|[一二三四五]面|面试题|手撕|笔试|面试官|问了|被问|拷打", re.I)


def ai_enabled() -> bool:
    return post_ai_filter_enabled() and bool(deepseek_api_key())


@dataclass
class PostVerdict:
    keep: bool
    role_id: str | None = None
    topics: list[str] = None  # type: ignore[assignment]
    reason: str = ""

    def __post_init__(self) -> None:
        if self.topics is None:
            self.topics = []


def _cache_path(name: str) -> Path:
    p = cache_dir() / "daily" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_CACHE_MEM: dict[str, dict] = {}


def load_cache(name: str) -> dict:
    if name in _CACHE_MEM:
        return _CACHE_MEM[name]
    path = _cache_path(name)
    if not path.is_file():
        _CACHE_MEM[name] = {}
        return _CACHE_MEM[name]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _CACHE_MEM[name] = {}
        return _CACHE_MEM[name]
    _CACHE_MEM[name] = data if isinstance(data, dict) else {}
    return _CACHE_MEM[name]


def save_cache(name: str, cache: dict) -> None:
    if cache:
        _cache_path(name).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        _CACHE_MEM[name] = cache


def clear_agent_caches() -> list[str]:
    removed: list[str] = []
    for name in ("post_ai_filter_cache.json", "question_answer_cache.json"):
        path = _cache_path(name)
        if path.is_file():
            path.unlink()
            removed.append(name)
    return removed


def chat_json(system: str, user: str) -> dict | None:
    from scripts.ai.gateway import chat_json as _gw_chat
    return _gw_chat(system, user, task="filter")


def _post_key(url: str, blob: str) -> str:
    return (url or "").strip() or hashlib.sha256(blob[:200].encode()).hexdigest()


def offline_post_keep(combined: str, *, has_images: bool = False) -> bool:
    plain = re.sub(r"\s+", "", combined)
    if not plain and not has_images:
        return False
    if len(plain) < 12 and not has_images:
        return False
    return bool(_OFFLINE_POST.search(combined))


# The model frequently ignores the "data|ai_app|null" instruction and emits
# free-form slugs (client_dev, candidate, test_dev, java_backend, game_client…).
# Collapse them to the canonical focus set so the ingest role filter works.
_OFF_ROLE_MARKERS = (
    "backend", "back_end", "frontend", "front_end", "fullstack", "full_stack",
    "test", "qa", "client", "game", "java", "c++", "cpp", "android", "ios",
    "embedded", "hardware", "firmware", "mobile", "sre", "security", "algorithm",
    "nlp", "design", "product", "candidate", "swe", "sde", "fae", "ic_",
    "vehicle", "server", "software", "app_dev", "app_soft", "interaction",
    "system_dev", "operation", "web",
)


# Titles that name another role explicitly — the model sometimes still tags these
# "data". A rule-based veto (only when no data/agent signal is present) overrides
# such misjudgments. Kept narrow to avoid false-dropping genuine data/AI posts.
_TITLE_OFF_ROLE = re.compile(
    r"(后端开发|客户端开发|客户端性能|游戏客户端|嵌入式|底软|测试开发|测开|软件测试|性能测试|"
    r"前端开发|Java\s*(开发|简历|后端|工程师)|C\+\+|golang|安卓开发|Android\s*开发|iOS\s*开发|"
    r"硬件开发|固件|驱动开发|运维开发|SRE|网络工程师|算法工程师|机器学习工程师|"
    r"半导体|晶圆|流片|光刻|蚀刻|封测|封装测试|工艺工程师|器件|良率|模拟IC|数字IC|"
    r"DRAM|NAND|FPGA|模拟电路|射频|通信工程|光通信|机械|材料|电气工程|结构工程)",
    re.I,
)
_TITLE_ON_ROLE = re.compile(
    r"数据开发|数仓|数开|大数据|数据研发|数据仓库|ETL|数据工程|实时数仓|湖仓|"
    r"Agent|智能体|RAG|大模型应用|LLM\s*应用|MCP|LangChain|AI\s*应用",
    re.I,
)


def _title_off_role(snippet: str) -> bool:
    """True when the post's head clearly names a non-target role and shows no
    data/agent signal — used to veto lenient AI role judgments."""
    head = (snippet or "")[:60]
    return bool(_TITLE_OFF_ROLE.search(head)) and not _TITLE_ON_ROLE.search(head)


def _focus_role_id(rid: str | None) -> str | None:
    """Map an AI-returned role_id (canonical or free-form) to data|ai_app|None."""
    r = (rid or "").strip().lower()
    if not r:
        return None
    canon = canonical_role_id(r)
    if canon in ("data", "ai_app"):
        return canon
    if any(m in r for m in _OFF_ROLE_MARKERS):
        return None
    if "data" in r:  # data_engineer, ai_data_engineer, data|ai_app …
        # data_analyst / data_scientist are NOT data-development roles
        if any(k in r for k in ("analyst", "scientist")):
            return None
        return "data"
    if any(k in r for k in ("ai_app", "agent", "rag", "llm", "mcp", "大模型", "ai应用", "llmapp")):
        return "ai_app"
    return None


def judge_post(snippet: str, *, url: str = "", cache: dict | None = None) -> PostVerdict | None:
    snip = re.sub(r"\s+", " ", (snippet or "").strip())[: post_ai_filter_max_chars()]
    if not snip:
        return PostVerdict(False, reason="empty")
    key = _post_key(url, snip)
    store = cache if cache is not None else load_cache("post_ai_filter_cache.json")
    off_role = _title_off_role(snip)
    if key in store and isinstance(store[key], dict):
        row = store[key]
        rid = None if off_role else _focus_role_id(str(row.get("role_id") or ""))
        return PostVerdict(
            bool(row.get("keep")),
            rid,
            [str(t) for t in row.get("topics") or []],
            str(row.get("reason") or ""),
        )
    data = chat_json(_POST_SYS, snip)
    if not data:
        return None
    verdict = PostVerdict(
        bool(data.get("keep")),
        None if off_role else _focus_role_id(str(data.get("role_id") or "")),
        [str(t) for t in (data.get("topics") or []) if t],
        str(data.get("reason") or ""),
    )
    if cache is not None:
        cache[key] = {
            "keep": verdict.keep,
            "role_id": verdict.role_id,
            "topics": verdict.topics,
            "reason": verdict.reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    return verdict


def cached_post_keep(url: str, blob: str) -> bool | None:
    if not ai_enabled():
        return None
    row = load_cache("post_ai_filter_cache.json").get(_post_key(url, blob))
    return bool(row.get("keep")) if isinstance(row, dict) else None


def _merge_batch(batch: list[tuple[int, Question]]) -> list[Question]:
    data = chat_json(_CLUSTER_SYS, json.dumps([{"id": str(i), "text": q.text[:280]} for i, q in batch], ensure_ascii=False))
    if not data:
        print(
            f"[ai_gate] cluster batch of {len(batch)} questions returned no AI data; "
            "passing through unmerged (check DEEPSEEK_API_KEY/network).",
            file=sys.stderr,
        )
        return [q for _, q in batch]

    drop = {int(x) for x in (data.get("drop") or []) if str(x).isdigit()}
    by_id = {i: q for i, q in batch}
    used: set[int] = set()
    out: list[Question] = []

    for grp in data.get("groups") or []:
        if not isinstance(grp, dict):
            continue
        ids = [int(x) for x in (grp.get("ids") or []) if str(x).isdigit() and int(x) in by_id]
        if not ids:
            continue
        canon = str(grp.get("canonical") or by_id[ids[0]].text).strip() or by_id[ids[0]].text
        # Guard against over-merge: a canonical that is just a category label
        # ("后端八股", "项目深挖") is not a question — use the longest member text.
        if len(canon) < 10 or canon in _TOPIC_LABELS:
            canon = max((by_id[i].text for i in ids), key=len)
        topic = str(grp.get("topic") or by_id[ids[0]].topic or "综合").strip() or "综合"
        merged = Question(text=canon, topic=topic, modality_origin=by_id[ids[0]].modality_origin, variants=[], freq=0)
        for idx in ids:
            used.add(idx)
            o = by_id[idx]
            if o.text != canon and o.text not in merged.variants:
                merged.variants.append(o.text)
            merged.freq += o.freq
            merged.latest_posted_at = _max_date(merged.latest_posted_at, o.latest_posted_at)
            _union(merged.source_refs, o.source_refs)
            _union(merged.role_tags, o.role_tags)
            _union(merged.company_tags, o.company_tags)
            if not merged.answer and o.answer:
                merged.answer = o.answer
        out.append(merged)

    for i, q in batch:
        if i not in used and i not in drop:
            out.append(q)
    return out


def _cluster_pass(questions: list[Question], *, batch_size: int) -> tuple[list[Question], bool]:
    """Returns (merged_questions, spanned_multiple_batches)."""
    indexed = list(enumerate(questions))
    if len(indexed) > batch_size * 2:
        indexed = list(enumerate(merge_similar_questions(questions, threshold=0.55)))

    merged: list[Question] = []
    for start in range(0, len(indexed), batch_size):
        if start:
            time.sleep(0.15)
        merged.extend(_merge_batch(indexed[start : start + batch_size]))
    result = dedupe_and_rank(merged) if merged else questions
    return result, len(indexed) > batch_size


def cluster_questions(
    questions: list[Question],
    *,
    batch_size: int = 35,
    offline_threshold: float = 0.68,
    today: date | None = None,
    max_passes: int = 3,
) -> list[Question]:
    if len(questions) < 2:
        return questions
    if not ai_enabled():
        merged = merge_similar_questions(questions, threshold=offline_threshold)
        return dedupe_and_rank(merged, today=today) if today else merged

    # A single pass only compares questions within the same batch of `batch_size`,
    # so duplicates landing in different batches survive. Re-run on the merged
    # output — batch composition shifts each pass as the list shrinks, so a later
    # pass can group questions that were split apart before — until a pass fits
    # in one AI batch (nothing left to compare across) or max_passes is hit.
    current = questions
    for _ in range(max_passes):
        current, spanned_multiple = _cluster_pass(current, batch_size=batch_size)
        if not spanned_multiple:
            break
    return current


_AUDIT_SYS = (
    "审核面试题库纯度。目标岗位：{role}。输入 [{{id,text}}]。"
    "判断每道题是否属于该岗位面试会考的内容（通用基础也算：SQL/数据库/操作系统/网络/Python 属于数据开发常考；"
    "LLM/RAG/Agent 属于 Agent 开发常考）。"
    "明显属于其他岗位的题（如 Qt/前端框架/硬件寄存器/ARM 汇编/iOS/Android 客户端）输出到 drop。"
    '拿不准的保留。JSON:{{"drop":["id",...]}}'
)


def audit_questions_role(questions: list[Question], role: str, *, batch_size: int = 40) -> list[Question]:
    """Post-cluster purity pass: drop questions that clearly belong to another role."""
    if not ai_enabled() or len(questions) < 5:
        return questions
    sys_prompt = _AUDIT_SYS.format(role=role or "数据开发")
    keep: list[Question] = []
    dropped = 0
    for start in range(0, len(questions), batch_size):
        chunk = questions[start : start + batch_size]
        payload = json.dumps([{"id": str(i), "text": q.text[:160]} for i, q in enumerate(chunk)], ensure_ascii=False)
        data = chat_json(sys_prompt, payload)
        drop_ids: set[int] = set()
        if isinstance(data, dict):
            drop_ids = {int(x) for x in (data.get("drop") or []) if str(x).isdigit()}
        for i, q in enumerate(chunk):
            if i in drop_ids:
                dropped += 1
            else:
                keep.append(q)
    if dropped:
        print(f"[ai_gate] role audit dropped {dropped}/{len(questions)} off-role questions", file=sys.stderr)
    return keep


def enrich_answers(questions: list[Question], role: str, *, top_n: int = 40, batch_size: int = 12) -> list[Question]:
    if not ai_enabled() or not questions:
        return questions
    cache = load_cache("question_answer_cache.json")
    pending: list[tuple[int, Question, str]] = []

    for i, q in enumerate(questions[:top_n]):
        if q.answer:
            continue
        ck = hashlib.sha256(q.text.strip().encode()).hexdigest()[:16]
        if ck in cache and cache[ck].get("answer"):
            q.answer = str(cache[ck]["answer"])
            continue
        pending.append((i, q, ck))

    for start in range(0, len(pending), batch_size):
        if start:
            time.sleep(0.15)
        chunk = pending[start : start + batch_size]
        payload = {"role": role, "items": [{"id": str(i), "text": q.text[:240], "topic": q.topic or "综合"} for i, q, _ in chunk]}
        data = chat_json(_ANSWER_SYS, json.dumps(payload, ensure_ascii=False))
        by_id = {}
        if isinstance(data, dict) and isinstance(data.get("answers"), list):
            by_id = {str(a.get("id")): str(a.get("answer") or "").strip() for a in data["answers"] if isinstance(a, dict)}
        for idx, q, ck in chunk:
            if ans := by_id.get(str(idx), "").strip():
                q.answer = ans
                cache[ck] = {"answer": ans, "at": datetime.now(timezone.utc).isoformat()}
    save_cache("question_answer_cache.json", cache)
    return questions
