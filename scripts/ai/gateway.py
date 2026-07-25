"""统一 AI Gateway — 所有 DeepSeek 调用经此分发。

功能：
- chat_json : 文本 → JSON（过滤/聚类/解答/追问链）
- vision_extract : 图片 → 结构化字段（Vision 补读）
- embed : 文本 → 向量（RAG）
- 统一缓存、模型路由、token 成本统计
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from scripts.config import (
    cache_dir,
    deepseek_api_base,
    deepseek_api_key,
    deepseek_model,
    deepseek_use_proxy,
)

# --------------------------------------------------------------------------- #
#  模型路由：便宜模型做过滤/聚类，强模型做 prep。                                   #
#  配置驱动 —— DEEPSEEK_MODEL / DEEPSEEK_PREP_MODEL 覆盖，避免上游改名后写死失效。   #
# --------------------------------------------------------------------------- #
def _model_for(task: str) -> str:
    from scripts.config import deepseek_model, deepseek_prep_model
    return deepseek_prep_model() if task == "prep" else deepseek_model()

# --------------------------------------------------------------------------- #
#  成本统计（内存，进程级）                                                       #
# --------------------------------------------------------------------------- #
_STATS: dict[str, int] = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
}


def get_stats() -> dict[str, int]:
    return dict(_STATS)


def reset_stats() -> None:
    _STATS.update({"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})


# --------------------------------------------------------------------------- #
#  缓存                                                                        #
# --------------------------------------------------------------------------- #
def _cache_path(name: str) -> Path:
    return cache_dir() / f"ai_{name}.json"


def _load_cache(name: str) -> dict:
    p = _cache_path(name)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(name: str, data: dict) -> None:
    p = _cache_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


# --------------------------------------------------------------------------- #
#  核心 HTTP helper                                                             #
# --------------------------------------------------------------------------- #
def _post_api(
    endpoint: str,
    body: dict,
    *,
    timeout: int = 30,
    retries: int = 3,
) -> dict | None:
    url = f"{deepseek_api_base()}{endpoint}"
    headers = {
        "Authorization": f"Bearer {deepseek_api_key()}",
        "Content-Type": "application/json",
    }
    trust_envs = (True, False) if deepseek_use_proxy() else (False,)
    for attempt in range(retries):
        if attempt:
            time.sleep(min(2.0 * (2 ** (attempt - 1)), 10.0))
        for trust_env in trust_envs:
            try:
                with requests.Session() as s:
                    s.trust_env = trust_env
                    resp = s.post(url, headers=headers, json=body, timeout=timeout)
                    if resp.status_code == 402:
                        raise RuntimeError("DeepSeek 账户余额不足，请充值后重试")
                    if resp.status_code == 429 or resp.status_code >= 500:
                        break  # retryable — next attempt with backoff
                    resp.raise_for_status()
                    return resp.json()
            except RuntimeError:
                raise
            except (requests.RequestException, ValueError):
                continue
    return None


# --------------------------------------------------------------------------- #
#  chat_json — 文本 → JSON dict                                                #
# --------------------------------------------------------------------------- #
def chat_json(
    system: str,
    user: str,
    *,
    task: str = "filter",
    cache_key: str | None = None,
    cache_name: str | None = None,
    timeout: int = 60,
) -> dict | None:
    """调用 DeepSeek 返回 JSON dict，支持缓存。"""
    if not deepseek_api_key():
        return None

    # 缓存查找
    if cache_key and cache_name:
        cache = _load_cache(cache_name)
        if cache_key in cache:
            return cache[cache_key]

    model = _model_for(task)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    result = _post_api("/v1/chat/completions", body, timeout=timeout)
    if not result:
        return None

    _STATS["calls"] += 1
    usage = result.get("usage") or {}
    _STATS["prompt_tokens"] += usage.get("prompt_tokens", 0)
    _STATS["completion_tokens"] += usage.get("completion_tokens", 0)

    try:
        raw = str(result["choices"][0]["message"]["content"]).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
    except (KeyError, json.JSONDecodeError, ValueError):
        return None

    # 写缓存
    if cache_key and cache_name:
        cache = _load_cache(cache_name)
        cache[cache_key] = data
        _save_cache(cache_name, cache)

    return data


# --------------------------------------------------------------------------- #
#  vision_extract — 图片 → 结构化字段                                           #
# --------------------------------------------------------------------------- #
_VISION_SYS = (
    "你是面经信息提取助手。从图片中提取面试题目和相关信息。"
    "JSON 格式输出，字段："
    '{"questions":["题目1","题目2"],'
    '"company":"公司名或空串",'
    '"round":"面试轮次或空串",'
    '"extraction_confidence":0.0~1.0,'
    '"raw_text":"图片中的完整文字"}'
)


def vision_enabled() -> bool:
    from scripts.config import vision_api_key
    return bool(vision_api_key())


def vision_extract(
    image_path: str | Path,
    *,
    extra_hint: str = "",
    cache_name: str = "vision_cache",
) -> dict | None:
    """
    调用多模态模型从图片中提取面经结构化信息。

    需配置 VISION_API_KEY（OpenAI 兼容端点，如通义 Qwen-VL / GLM-4V）；
    DeepSeek 无视觉端点，未配置时返回 None（调用方保持 OCR 结果）。

    返回:
        {questions, company, round, extraction_confidence, raw_text}
    """
    from scripts.config import vision_api_base, vision_api_key, vision_model

    if not vision_api_key():
        return None

    image_path = Path(image_path)
    if not image_path.exists():
        return None

    ck = _cache_key(str(image_path), str(image_path.stat().st_mtime))
    cache = _load_cache(cache_name)
    if ck in cache:
        return cache[ck]

    # 读取图片并 base64 编码
    try:
        img_data = image_path.read_bytes()
        suffix = image_path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(suffix, "image/jpeg")
        b64 = base64.b64encode(img_data).decode("ascii")
    except OSError:
        return None

    user_content: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        },
        {
            "type": "text",
            "text": f"请提取图片中的面试题目和信息。{extra_hint}",
        },
    ]

    body = {
        "model": vision_model(),
        "messages": [
            {"role": "system", "content": _VISION_SYS},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": 1024,
    }
    url = f"{vision_api_base()}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {vision_api_key()}", "Content-Type": "application/json"}
    result = None
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=90)
        resp.raise_for_status()
        result = resp.json()
    except (requests.RequestException, ValueError):
        return None
    if not result or not result.get("choices"):
        return None

    _STATS["calls"] += 1
    usage = result.get("usage") or {}
    _STATS["prompt_tokens"] += usage.get("prompt_tokens", 0)
    _STATS["completion_tokens"] += usage.get("completion_tokens", 0)

    try:
        raw = str(result["choices"][0]["message"]["content"]).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
    except (KeyError, json.JSONDecodeError, ValueError):
        return None

    cache[ck] = data
    _save_cache(cache_name, cache)
    return data


# --------------------------------------------------------------------------- #
#  embed — 文本 → 向量（为 RAG 预留）                                           #
# --------------------------------------------------------------------------- #
def embed(texts: list[str], *, model: str = "text-embedding-v3") -> list[list[float]] | None:
    """调用 embedding 接口，返回向量列表。"""
    if not deepseek_api_key() or not texts:
        return None
    body = {"model": model, "input": texts}
    result = _post_api("/v1/embeddings", body)
    if not result:
        return None
    try:
        items = sorted(result["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
    except (KeyError, TypeError):
        return None
