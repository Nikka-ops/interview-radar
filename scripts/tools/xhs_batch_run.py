"""小红书温和批量抓取 — 单轮 35 词(带抖动),供计划任务每 4 小时调用一次。

scrape_state 记录已抓关键词，每轮自动取「最久未抓」的一批，2-3 天轮转覆盖全量。
遇验证码/风控立即停当轮（保留已抓），下一轮继续。抓完 --import-only 交给日常重建。
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import date

from scripts.config import bootstrap_env
from scripts.corpus.company_catalog import resolve_company_list
from scripts.corpus.tech_roles import resolve_role_label
from scripts.scrape.keywords import xhs_keywords_for_role
from scripts.scrape.scrape_health import NEXT_STEP_XHS_AUTH, record
from scripts.scrape.scrape_state import load_scrape_state, save_scrape_state
from scripts.scrape.xhs_export import run_safe_xhs_scrape

def _batch_size() -> int:
    """单轮词数，读 XHS_MAX_KEYWORDS_PER_RUN（默认 35）；账号受限时调小。"""
    from scripts.config import xhs_max_keywords_per_run
    return xhs_max_keywords_per_run()


def _next_keywords(state: dict, role_id: str, pool: list[str], n: int) -> list[str]:
    """取最久未抓的 n 个关键词（round-robin 覆盖全量）。"""
    seen: dict = state.setdefault("xhs_kw_last", {}).setdefault(role_id, {})
    ranked = sorted(pool, key=lambda k: seen.get(k, ""))  # 空串（从未抓）排最前
    return ranked[:n]


def main(argv: list[str] | None = None) -> int:
    bootstrap_env()
    role_id = (argv[0] if argv else "data").strip() or "data"
    role_label = resolve_role_label(role_id=role_id)
    companies = resolve_company_list("all")
    pool = xhs_keywords_for_role(role_id, companies)

    state = load_scrape_state()
    batch = _next_keywords(state, role_id, pool, _batch_size())
    if not batch:
        print("关键词池为空"); return 0

    print(f"[{role_label}] 本轮 {len(batch)}/{len(pool)} 词（逐词断点续抓）", flush=True)
    from scripts.config import xhs_batch_pause_seconds
    from scripts.scrape.scrape_progress import set_progress, clear_progress

    pause = xhs_batch_pause_seconds()
    now = date.today().isoformat()
    done = 0
    for i, kw in enumerate(batch):
        set_progress("scraping", f"抓取小红书：{kw}（第 {i + 1}/{len(batch)} 词）",
                     current=i + 1, total=len(batch))
        if i:
            # 词间抖动间隔(真人节奏,防行为检测)
            time.sleep(pause + random.uniform(0, pause))
        try:
            run_safe_xhs_scrape([kw], batch_size=1, pause_seconds=0, limit_keywords=False)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if any(m in msg for m in ("验证", "登录", "过期", "风控", "461")):
                # 登录失效/风控/验证码 → 立即停止,已完成的词保持记账,下轮从断点续
                record("xiaohongshu", status="risk_control",
                       detail=f"{kw}: {msg[:150]}", next_step=NEXT_STEP_XHS_AUTH)
                print(f"[{role_label}] 第 {i + 1} 词触发风控/失效，停止本轮（已完成 {done} 词已记账）", file=sys.stderr)
                clear_progress()
                return 1
            # 单词无结果/瞬时错误 → 跳过但仍标记(避免下轮反复卡在坏词)
            print(f"[{role_label}] 第 {i + 1} 词 '{kw}' 跳过: {msg[:60]}", file=sys.stderr)
        # 每词抓完立即落盘标记 → 断点即为此处
        state["xhs_kw_last"][role_id][kw] = now
        save_scrape_state(state)
        done += 1

    clear_progress()
    record("xiaohongshu", status="ok", detail=f"{role_label} 逐词 {done}/{len(batch)} 词", count=done)
    print(f"[{role_label}] 本轮完成 {done}/{len(batch)} 词", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
