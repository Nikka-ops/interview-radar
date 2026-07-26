"""Consolidated: test_corpus_ingest.py, test_classify.py, test_quality.py, test_pipeline.py, test_extract_questions.py, test_semantic_merge.py, test_dedupe_rank.py, test_clusters.py, test_group.py, test_export_personalize.py, test_bank_cache.py, test_merged_role_bundle.py, test_posts_view.py, test_post_format.py, test_post_text_merge.py, test_store.py, test_models.py, test_ingest_fallback.py, test_corpus_sync.py, test_company_catalog.py, test_company_normalize.py, test_interview_link.py"""


# --- test_corpus_ingest.py ---

from datetime import date

from scripts.corpus.post_dedupe import dedupe_raw_posts
from scripts.corpus.post_filter import filter_ingest_posts, should_drop
from scripts.corpus.recency import RECENCY_WINDOW_DAYS, filter_recent
from scripts.corpus.role_match import (
    filter_posts_for_bank,
    infer_preset_from_post,
    infer_preset_from_text,
    matches_target_role,
    refine_extracted_role,
)
from scripts.corpus.tech_roles import (
    DEFAULT_ROLE_ID,
    canonical_role_id,
    equivalent_role_ids,
    get_tech_role,
    list_tech_roles,
    resolve_role_label,
)
from scripts.models import RawPost


def _post(posted_at):
    return RawPost("nowcoder", "u", "text", "Q", posted_at=posted_at)


# --- post_filter (agent-first) ---


def test_offline_drops_non_interview():
    post = RawPost("xiaohongshu", "https://xhs.com/chat", "text", "今年就业方向 感觉没什么面试")
    assert should_drop(post)


def test_offline_keeps_interview_recap():
    post = RawPost(
        "nowcoder",
        "https://nowcoder.com/1",
        "text",
        "字节 AI 应用开发一面面经\n1. 介绍项目\n2. RAG 链路怎么设计？",
    )
    assert not should_drop(post)


def test_offline_drops_customs_trade_marketing():
    post = RawPost(
        source="xiaohongshu",
        url="https://xhs.com/customs",
        post_type="image",
        raw_text="用海关数据开发 关键是看这六个能力\n做了这么多年外贸，见过太多人吐槽海关数据没用",
        asset_paths=["https://img/a.jpg"],
        image_ocr_text="1. 数据筛选能力\n2. 客户开发能力\n外贸交易数据",
    )
    assert should_drop(post)


def test_filter_ingest_ai_drops_noise(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")
    posts = [
        RawPost("xiaohongshu", "https://xhs.com/ok", "text", "阿里数开一面\n1. Hive 分区"),
        RawPost("xiaohongshu", "https://xhs.com/ask", "text", "求助：有没有腾讯数仓面经啊"),
        RawPost("xiaohongshu", "https://xhs.com/ad", "text", "数仓面试辅导班，私信领取资料"),
    ]

    def fake(snippet, **kwargs):
        from scripts.corpus.ai_gate import PostVerdict

        if "辅导班" in snippet or "求助" in snippet:
            return PostVerdict(False, reason="noise")
        return PostVerdict(True, role_id="data")

    monkeypatch.setattr("scripts.corpus.post_filter.judge_post", fake)
    kept, meta = filter_ingest_posts(posts, "数据开发", use_ai=True)
    assert len(kept) == 1
    assert meta.get("ai_dropped") == 2


def test_filter_ingest_without_ai():
    posts = [
        RawPost("nowcoder", "https://nowcoder.com/ok", "text", "美团二面\n1. Agent 架构"),
        RawPost("xiaohongshu", "https://xhs.com/chat", "text", "今年就业方向 感觉没什么面试"),
    ]
    kept, meta = filter_ingest_posts(posts, "Agent 开发", use_ai=False)
    assert len(kept) == 1
    assert meta["ai_enabled"] is False


def test_filter_ingest_ai(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")

    posts = [
        RawPost("xiaohongshu", "https://xhs.com/border", "text", "分享下求职体会"),
        RawPost("nowcoder", "https://nowcoder.com/ok", "text", "美团二面\n1. Agent 架构"),
        RawPost("nowcoder", "https://nowcoder.com/java", "text", "腾讯 Java 后端二面\n1. Spring"),
    ]

    def fake(snippet, **kwargs):
        from scripts.corpus.ai_gate import PostVerdict

        if "求职体会" in snippet:
            return PostVerdict(False)
        if "Java 后端" in snippet:
            return PostVerdict(True, role_id="backend")
        return PostVerdict(True, role_id="ai_app")

    monkeypatch.setattr("scripts.corpus.post_filter.judge_post", fake)
    kept, meta = filter_ingest_posts(posts, "Agent 开发", use_ai=True)
    assert len(kept) == 1
    assert meta.get("ai_dropped") == 2


def test_filter_ingest_ai_network_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")

    post = RawPost(
        "nowcoder",
        "https://nowcoder.com/ok",
        "text",
        "数据开发岗 Spark Hive 数仓分层与 ETL 流水线实践记录 " * 3,
        role="数据开发",
    )
    monkeypatch.setattr("scripts.corpus.post_filter.judge_post", lambda *a, **k: None)
    kept, meta = filter_ingest_posts([post], "数据开发", use_ai=True)
    assert len(kept) == 0
    assert meta.get("ai_fallback_dropped") == 1 or meta.get("offline_dropped") == 1


def test_filter_ingest_ai_network_fallback_keeps_interview(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")

    post = RawPost(
        "nowcoder",
        "https://nowcoder.com/ok",
        "text",
        "阿里数据开发一面\n1. Spark shuffle\n2. 数仓分层",
        role="数据开发",
    )
    monkeypatch.setattr("scripts.corpus.post_filter.judge_post", lambda *a, **k: None)
    kept, meta = filter_ingest_posts([post], "数据开发", use_ai=True)
    assert len(kept) == 1
    assert meta.get("ai_fallback_kept") == 1

# --- role_match ---


def test_infer_qa_over_llm_for_cekai_title():
    preset = infer_preset_from_text("字节春招大模型测开一面面经")
    assert preset is not None
    assert preset.id == "qa"


def test_refine_extracted_role_maps_to_preset():
    role = refine_extracted_role(title="美团 Agent 方向面经整理")
    assert role is not None
    assert role in {"Agent 开发", "AI 应用开发", "AI/Agent 应用开发"}


def test_infer_preset_from_post_prefers_title_line():
    post = RawPost(
        source="nowcoder",
        url="https://example.com/1",
        post_type="text",
        raw_text="领境科技前端开发面经\n后面是正文…",
    )
    assert infer_preset_from_post(post).id == "frontend"


def test_filter_drops_mismatched_post():
    bad = RawPost(
        source="nowcoder",
        url="https://example.com/1",
        post_type="text",
        raw_text="字节测开一面：自动化测试框架怎么设计",
        role="测试开发",
    )
    good = RawPost(
        source="nowcoder",
        url="https://example.com/2",
        post_type="text",
        raw_text="大模型 RLHF 训练流程与 SFT 数据构造",
        role="大模型",
    )
    kept, dropped = filter_posts_for_bank([bad, good], "大模型")
    assert len(kept) == 1 and kept[0].url.endswith("/2")
    assert len(dropped) == 1


def test_related_ai_roles_match():
    post = RawPost(
        source="nowcoder",
        url="https://example.com/3",
        post_type="text",
        raw_text="RAG 检索增强与 Agent 工具调用面经",
        role="AI 应用开发",
    )
    assert matches_target_role(post, "Agent开发") is True


def test_data_title_beats_spark_in_body():
    post = RawPost(
        source="nowcoder",
        url="https://example.com/1",
        post_type="text",
        raw_text="字节 Agent 开发一面\n项目里用 Spark 做特征，问了 RAG 链路",
        role="Agent 开发",
    )
    assert infer_preset_from_post(post).id == "ai_app"


def test_data_analyst_not_in_data_bank():
    analyst = RawPost(
        source="nowcoder",
        url="https://example.com/a",
        post_type="text",
        raw_text="美团数据分析一面\n1. SQL窗口函数\n2. AB实验设计",
        role="数据分析",
    )
    kept, dropped = filter_posts_for_bank([analyst], "数据开发")
    assert len(kept) == 0 and len(dropped) == 1


def test_agent_post_not_in_data_bank():
    agent = RawPost(
        source="xiaohongshu",
        url="https://example.com/b",
        post_type="text",
        raw_text="腾讯 Agent 开发二面\n1. MCP 工具调用\n2. RAG 评测",
        role="Agent 开发",
    )
    kept, _ = filter_posts_for_bank([agent], "数据开发")
    assert len(kept) == 0


def test_backend_post_not_in_data_bank():
    post = RawPost(
        source="nowcoder",
        url="https://example.com/be",
        post_type="text",
        raw_text="腾讯 Java 后端二面\n1. Spring Boot\n2. MySQL 索引",
        role="后端开发",
    )
    kept, _ = filter_posts_for_bank([post], "数据开发")
    assert len(kept) == 0


def test_wxg_post_company_is_tencent():
    from scripts.corpus.posts_view import post_company

    post = RawPost(
        source="nowcoder",
        url="https://example.com/wxg",
        post_type="text",
        raw_text="WXG 后台开发一面\n1. 网络编程",
    )
    assert post_company(post) == "腾讯"


    agent = RawPost(
        source="xiaohongshu",
        url="https://example.com/b",
        post_type="text",
        raw_text="腾讯 Agent 开发二面\n1. MCP 工具调用\n2. RAG 评测",
        role="Agent 开发",
    )
    kept, _ = filter_posts_for_bank([agent], "数据开发")
    assert len(kept) == 0


def test_data_post_kept_in_data_bank():
    data = RawPost(
        source="nowcoder",
        url="https://example.com/c",
        post_type="text",
        raw_text="阿里数据开发一面\n1. Spark shuffle 优化\n2. 数仓分层 ODS/DWD",
        role="数据开发",
    )
    kept, _ = filter_posts_for_bank([data], "数据开发")
    assert len(kept) == 1 and kept[0].url.endswith("/c")


def test_ambiguous_post_dropped_from_data_bank():
    vague = RawPost(
        source="xiaohongshu",
        url="https://example.com/d",
        post_type="text",
        raw_text="互联网大厂面经分享\n今天聊了下项目经历",
    )
    assert matches_target_role(vague, "数据开发") is False
    kept, _ = filter_posts_for_bank([vague], "数据开发")
    assert len(kept) == 0


def test_embedded_hr_post_not_in_data_bank():
    post = RawPost(
        source="xiaohongshu",
        url="https://example.com/embed",
        post_type="text",
        raw_text="一天面了6个嵌入式开发，水平真的令人堪忧\n候选人任务调度经验不足",
    )
    kept, _ = filter_posts_for_bank([post], "数据开发")
    assert len(kept) == 0


def test_infer_data_from_warehouse_title():
    preset = infer_preset_from_text("字节跳动 数仓工程师 一面面经")
    assert preset is not None and preset.id == "data"


# --- tech_roles ---


def test_list_tech_roles_has_core_jobs():
    labels = {r["label"] for r in list_tech_roles()}
    assert {"后端开发", "算法工程师", "Agent 开发", "数据开发", "测试开发"} <= labels


def test_resolve_role_label_by_id():
    assert resolve_role_label(role_id="backend") == "后端开发"
    assert resolve_role_label(role_id="agent") == "Agent 开发"
    assert resolve_role_label(role_id="ai_app") == "Agent 开发"
    assert resolve_role_label(role_id="data") == "数据开发"


def test_resolve_role_label_custom_text():
    assert resolve_role_label(role_text="游戏客户端") == "游戏客户端"


def test_default_role():
    assert get_tech_role(DEFAULT_ROLE_ID) is not None


def test_canonical_and_equivalent_role_ids():
    assert canonical_role_id("agent") == "ai_app"
    assert set(equivalent_role_ids("ai_app")) == {"ai_app", "agent"}
    assert equivalent_role_ids("backend") == ["backend"]


# --- recency / dedupe ---


def test_default_window_is_three_months():
    assert RECENCY_WINDOW_DAYS == 90


def test_keeps_recent_drops_old():
    ref = date(2026, 5, 28)
    kept = filter_recent([_post("2026-04-01"), _post("2024-01-01")], window_days=90, today=ref)
    assert [p.posted_at for p in kept] == ["2026-04-01"]


def test_none_dates_are_kept():
    ref = date(2026, 5, 28)
    kept = filter_recent([_post(None), _post("2010-01-01")], window_days=90, today=ref)
    assert [p.posted_at for p in kept] == [None]


def test_unparseable_date_is_kept():
    ref = date(2026, 5, 28)
    kept = filter_recent([_post("not-a-date")], window_days=90, today=ref)
    assert len(kept) == 1


def test_boundary_exactly_window_is_kept():
    ref = date(2026, 5, 28)
    kept = filter_recent([_post("2026-03-30")], window_days=90, today=ref)
    assert len(kept) == 1


def test_dedupe_raw_posts_by_url():
    a = RawPost("nowcoder", "https://www.nowcoder.com/feed/main/detail/abc", "text", "same")
    b = RawPost("nowcoder", "https://www.nowcoder.com/feed/main/detail/abc", "text", "dup")
    assert len(dedupe_raw_posts([a, b])) == 1

# --- test_classify.py ---

from scripts.corpus.classify import classify_search_queries, extract_company_role, infer_company_from_text


def test_infer_company_from_body_text():
    assert infer_company_from_text("今天面试字节跳动大模型岗位") == "字节跳动"
    assert infer_company_from_text("美团 Agent 方向技术面") == "美团"


def test_extract_company_from_desc_when_title_missing():
    company, role = extract_company_role(title="面经分享", desc="腾讯后端开发一面总结")
    assert company == "腾讯"


def test_extract_company_role_from_nowcoder_style_title():
    company, role = extract_company_role(title="字节 AI 应用开发 一面面经")
    assert company == "字节跳动"
    assert role == "Agent 开发"


def test_extract_company_role_from_xhs_title():
    company, role = extract_company_role(title="腾讯 产品经理 实习 面经")
    assert company == "腾讯"
    assert "产品" in role


def test_extract_company_role_from_tags():
    company, role = extract_company_role(
        title="某厂面经分享",
        tags=["#字节", "AI应用开发"],
    )
    assert company == "字节跳动"
    assert role == "Agent 开发"


def test_extract_company_role_from_bracketed_nowcoder_title():
    company, role = extract_company_role(title="【面试真题】字节 AI 应用岗")
    assert company == "字节跳动"
    assert role == "Agent 开发"


def test_extract_company_role_from_meituan_agent_direction():
    company, role = extract_company_role(title="【面试真题】美团Agent 方向面经整理")
    assert company == "美团"
    assert role in {"Agent 开发", "AI 应用开发", "AI/Agent 应用开发"}


def test_extract_returns_none_for_unlabeled_title():
    company, role = extract_company_role(title="无日期帖", desc="今天天气不错，随便聊聊。")
    assert company is None
    assert role is None


def test_extract_rejects_year_as_company():
    company, role = extract_company_role(title="【面经分享】2026 Java 后端开发 面经")
    assert company is None
    assert role is not None
    assert "Java" in role or "后端" in role


def test_classify_search_queries_data_role_extra_terms():
    queries = classify_search_queries(roles=["数据开发"], role_id="data")
    assert "数仓工程师 面经" in queries
    assert "Flink开发 面经" in queries
    assert "数据开发工程师 面经" in queries


def test_classify_search_queries_builds_role_and_company_batches():
    queries = classify_search_queries(
        roles=["AI 应用开发", "产品经理"],
        companies=["字节跳动", "腾讯"],
    )
    assert "AI 应用开发 面经" in queries
    assert "字节跳动 AI 应用开发 面经" in queries
    assert "腾讯 产品经理 实习 面经" in queries
    assert len(queries) == len(set(queries))

# --- test_quality.py ---

from scripts.corpus.quality import (
    clean_question_text,
    filter_by_companies,
    is_interview_question,
    is_low_quality_question,
    is_narrative_commentary,
)
from scripts.models import Question


def test_clean_question_strips_xhs_marker():
    assert clean_question_text("[一R] attention 公式？") == "attention 公式？"


def test_is_low_quality_narrative():
    assert is_low_quality_question("首先声明楼主是菜鸡这是一段很长的感受没有问号")


def test_filter_by_companies_keeps_unlabeled():
    qs = [
        Question("通用题？", company_tags=[]),
        Question("字节题？", company_tags=["字节跳动"]),
        Question("腾讯题？", company_tags=["腾讯"]),
    ]
    out = filter_by_companies(qs, ["字节跳动"])
    assert len(out) == 2
    texts = {q.text for q in out}
    assert "字节题？" in texts
    assert "通用题？" in texts


def test_rejects_advice_narrative_not_question():
    text = (
        "建议想要应聘新点算法岗的牛友好好背背基础八股，感觉一面不怎么拷打项目，"
        "中心还是在八股吧。问的是数据预处理流程，模型部署步骤之类的八股，"
        "不过我光顾着背改进原因了没背八股"
    )
    assert is_narrative_commentary(text)
    assert not is_interview_question(text)


def test_accepts_real_question_with_question_mark():
    assert is_interview_question("分支覆盖率是怎么统计的？原理有没有了解过？")
    assert is_interview_question("RAG 检索链路怎么设计？")


def test_accepts_short_ask_prompt():
    assert is_interview_question("介绍一下你做的项目和技术亮点")

# --- test_pipeline.py ---

from scripts.corpus.pipeline import build_ranked_questions
from scripts.models import RawPost


def test_pipeline_semantic_merge_reduces_duplicates():
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/a",
            post_type="text",
            raw_text="1. MCP 和 Skill 的区别？\n2. MCP 与 Skill 有何区别？",
            posted_at="2026-05-01",
        )
    ]
    ranked = build_ranked_questions(posts, semantic_merge=True, merge_threshold=0.5)
    assert len(ranked) == 1
    assert ranked[0].freq >= 2

# --- test_extract_questions.py ---

from scripts.corpus.extract_questions import extract_questions, extract_questions_from_post, infer_topic
from scripts.models import RawPost


def test_infer_topic_rag():
    assert infer_topic("RAG 召回率低怎么排查？") == "RAG"


def test_infer_topic_spark_hive():
    assert infer_topic("Spark shuffle 和 Hive 分区有什么区别？") == "Spark/计算"
    assert infer_topic("ODS DWD 分层设计") == "数仓建模"


def test_extract_numbered_questions_from_post():
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/discuss/1",
        post_type="text",
        raw_text=(
            "一面 50min\n"
            "1. embedding 向量检索的原理是什么？\n"
            "2. function calling 如何解析用户意图？\n"
            "感受：很难"
        ),
        posted_at="2026-03-01",
        company="字节跳动",
        role="AI 应用开发",
    )
    qs = extract_questions_from_post(post)
    texts = [q.text for q in qs]
    assert any("embedding" in t for t in texts)
    assert any("function calling" in t for t in texts)
    assert all(q.company_tags == ["字节跳动"] for q in qs)


def test_extract_skips_noise_lines():
    post = RawPost(
        source="xiaohongshu",
        url="https://www.xiaohongshu.com/explore/n1",
        post_type="text",
        raw_text="点赞收藏关注\n#面经分享#",
    )
    assert extract_questions_from_post(post) == []


def test_extract_inline_numbered_on_same_line():
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/discuss/x",
        post_type="text",
        raw_text=(
            "你们的测试数据里会不会涉及敏感信息？有没有风险？ "
            "18. 这个分析平台的技术难点在哪里？ "
            "19. 为什么最终选择了OpenAI的模型？"
        ),
        company="字节跳动",
    )
    qs = extract_questions_from_post(post)
    texts = [q.text for q in qs]
    assert len(texts) >= 2
    assert any("敏感信息" in t for t in texts)
    assert any("OpenAI" in t or "分析平台" in t for t in texts)


def test_extract_from_image_ocr_text():
    post = RawPost(
        source="xiaohongshu",
        url="https://www.xiaohongshu.com/explore/n2",
        post_type="image",
        raw_text="图片面经",
        content_text="图片面经",
        image_ocr_text="1. RAG 检索怎么做？\n2. Agent 工具调用怎么设计？",
        extraction_quality="ocr_ok",
        company="美团",
        role="AI 应用开发",
    )
    qs = extract_questions_from_post(post)
    assert len(qs) == 2
    assert qs[0].modality_origin == "ocr"


def test_extract_questions_across_posts():
    posts = [
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/a",
            post_type="text",
            raw_text="问了 MCP 和 Skill 的区别？",
            company="字节跳动",
        ),
        RawPost(
            source="nowcoder",
            url="https://www.nowcoder.com/discuss/b",
            post_type="text",
            raw_text="问了 mcp 和 skill 的区别？",
            company="字节跳动",
        ),
    ]
    qs = extract_questions(posts)
    assert len(qs) == 2

# --- test_semantic_merge.py ---

from scripts.corpus.semantic_merge import merge_similar_questions, similarity
from scripts.models import Question


def test_similarity_high_for_paraphrase():
    a = "RAG 召回率低怎么排查"
    b = "RAG 召回率低怎么排查"
    assert similarity(a, b) == 1.0


def test_merge_similar_questions_combines_freq():
    qs = [
        Question("MCP 和 Skill 的区别", ["u1"], company_tags=["字节跳动"]),
        Question("MCP 和 Skill 区别", ["u2"], company_tags=["字节跳动"]),
        Question("Transformer attention 公式", ["u3"]),
    ]
    merged = merge_similar_questions(qs, threshold=0.5)
    assert len(merged) == 2
    mcp = next(q for q in merged if "MCP" in q.text)
    assert mcp.freq == 2
    assert "MCP 和 Skill 区别" in mcp.variants

# --- test_dedupe_rank.py ---

from datetime import date

from scripts.models import Question
from scripts.corpus.dedupe_rank import normalize, dedupe_and_rank


def test_normalize_strips_case_punctuation_whitespace():
    assert normalize("  What is  MCP??  ") == normalize("what is mcp")


def test_dedupe_merges_and_sums_freq():
    qs = [
        Question("What is MCP?", ["u1"], role_tags=["agent"]),
        Question("what is  mcp", ["u2"], role_tags=["llm"]),
        Question("What is RAG?", ["u3"]),
    ]
    out = dedupe_and_rank(qs)
    assert len(out) == 2
    top = out[0]
    assert top.freq == 2
    assert top.source_refs == ["u1", "u2"]
    assert top.role_tags == ["agent", "llm"]


def test_dedupe_merges_company_tags():
    qs = [
        Question("What is MCP?", ["u1"], company_tags=["字节跳动"]),
        Question("what is  mcp", ["u2"], company_tags=["腾讯"]),
    ]
    out = dedupe_and_rank(qs)
    assert out[0].company_tags == ["字节跳动", "腾讯"]


def test_rank_sorts_by_freq_desc():
    qs = [
        Question("rare", ["a"]),
        Question("common", ["b"]),
        Question("common", ["c"]),
    ]
    out = dedupe_and_rank(qs)
    assert out[0].text == "common"
    assert out[0].freq == 2
    assert out[1].text == "rare"


def test_merge_keeps_most_recent_date():
    qs = [
        Question("What is MCP?", ["u1"], latest_posted_at="2024-01-01"),
        Question("what is  mcp", ["u2"], latest_posted_at="2025-06-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert len(out) == 1
    assert out[0].latest_posted_at == "2025-06-01"
    assert out[0].freq == 2


def test_recency_weight_can_outrank_lower_freq_when_close():
    # old item freq=2 → score 2*0.3=0.6 ; fresh item freq=1 → score 1*1.0=1.0
    qs = [
        Question("old hot", ["a"], freq=2, latest_posted_at="2023-01-01"),
        Question("fresh", ["b"], freq=1, latest_posted_at="2026-04-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert out[0].text == "fresh"


def test_undated_ranks_below_known_stale():
    # New policy: undated (0.2) ranks BELOW known-stale (0.3).
    # freq all 1: fresh(1.0) > stale(0.3) > undated(0.2)
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("undated", ["b"], latest_posted_at=None),
        Question("fresh", ["c"], latest_posted_at="2026-05-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["fresh", "stale", "undated"]


def test_malformed_date_treated_as_undated():
    # Malformed posted_at should weight the same as None (0.2), i.e. rank below known-stale.
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("garbled", ["b"], latest_posted_at="not-a-date"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["stale", "garbled"]

# --- test_clusters.py ---

from datetime import date

from scripts.corpus.clusters import assign_cluster_ids, build_clusters
from scripts.corpus.dedupe_rank import _recency_weight
from scripts.models import Question


def test_assign_cluster_ids():
    qs = [Question("A", freq=2), Question("B", freq=1)]
    assign_cluster_ids(qs)
    assert qs[0].cluster_id == "c001"
    assert qs[1].cluster_id == "c002"


def test_build_clusters_ranked_by_batch():
    qs = [
        Question("RAG 怎么优化", freq=3, topic="RAG", variants=["RAG 优化方法"]),
        Question("Agent 记忆", freq=1, topic="Agent"),
    ]
    assign_cluster_ids(qs)
    ref = date(2026, 6, 18)
    clusters = build_clusters(qs, ref_score_fn=lambda q: q.freq * _recency_weight(q.latest_posted_at, ref))
    assert clusters[0]["rank"] == 1
    assert clusters[0]["batch_count"] == 3
    assert clusters[0]["variants"] == ["RAG 优化方法"]

# --- test_group.py ---

from scripts.corpus.group import group_posts_by_taxonomy, taxonomy_summary
from scripts.models import RawPost


def test_group_posts_by_taxonomy():
    posts = [
        RawPost("nowcoder", "u1", "text", "q1", company="字节跳动", role="AI 应用开发"),
        RawPost("xiaohongshu", "u2", "image", "q2", company="字节跳动", role="AI 应用开发"),
        RawPost("nowcoder", "u3", "text", "q3", company="腾讯", role="产品经理"),
        RawPost("nowcoder", "u4", "text", "q4"),
    ]
    grouped = group_posts_by_taxonomy(posts)
    assert len(grouped["字节跳动"]["AI 应用开发"]) == 2
    assert len(grouped["腾讯"]["产品经理"]) == 1
    assert len(grouped["未标注"]["未标注"]) == 1


def test_taxonomy_summary_counts_sources():
    posts = [
        RawPost("nowcoder", "u1", "text", "q1", company="字节跳动", role="AI 应用开发"),
        RawPost("xiaohongshu", "u2", "image", "q2", company="字节跳动", role="AI 应用开发"),
    ]
    rows = taxonomy_summary(posts)
    assert rows[0]["company"] == "字节跳动"
    assert rows[0]["role"] == "AI 应用开发"
    assert rows[0]["count"] == 2
    assert set(rows[0]["sources"]) == {"nowcoder", "xiaohongshu"}

# --- test_export_personalize.py ---

from datetime import date

from scripts.corpus.dedupe_rank import dedupe_and_rank
from scripts.corpus.export_bank import build_question_bank, render_frequency_report
from scripts.corpus.personalize import (
    build_followup_chains,
    predict_questions,
    score_resume_match,
)
from scripts.models import Question


def _sample_ranked() -> list[Question]:
    qs = [
        Question(
            "RAG 召回率低怎么排查？",
            ["u1"],
            freq=1,
            company_tags=["字节跳动"],
            role_tags=["AI 应用开发"],
            topic="RAG",
            latest_posted_at="2026-04-01",
        ),
        Question(
            "Agent 短期记忆和长期记忆怎么设计？",
            ["u2"],
            freq=1,
            topic="Agent",
            latest_posted_at="2026-03-01",
        ),
    ]
    return dedupe_and_rank(qs, today=date(2026, 6, 18))


def test_build_question_bank_structure():
    ranked = _sample_ranked()
    bank = build_question_bank(
        role="AI 应用开发",
        companies=["字节跳动"],
        ranked=ranked,
        post_count=5,
        sources_meta={"nowcoder": {"count": 5}},
    )
    assert bank["role"] == "AI 应用开发"
    assert bank["question_count"] == 2
    assert bank["cluster_count"] == 2
    assert bank["clusters"][0]["rank"] == 1
    assert bank["recency_window_days"] == 90
    assert bank["questions"][0]["confidence"] in {"高频", "中频", "低频"}
    assert bank["taxonomy"]


def test_render_frequency_report_contains_top():
    ranked = _sample_ranked()
    bank = build_question_bank(
        role="AI 应用开发",
        companies=[],
        ranked=ranked,
        post_count=2,
        sources_meta={},
    )
    md = render_frequency_report(bank, top_n=5)
    assert "高频题簇 Top" in md
    assert "RAG" in md


def test_resume_match_prefers_overlap():
    q = Question("Python RAG 项目里 embedding 召回怎么优化？", topic="RAG")
    resume = "项目: RAG 知识库 Python embedding 检索优化"
    assert score_resume_match(q, resume, role="AI 应用开发") >= 0.2


def test_predict_and_followup_chains():
    ranked = _sample_ranked()
    resume = "技能: Python LangChain RAG Pinecone"
    predicted = predict_questions(ranked, resume, role="AI 应用开发", top_n=5)
    assert predicted
    assert "combined_score" in predicted[0]
    chains = build_followup_chains(predicted, resume, max_chains=2)
    assert len(chains) == 2
    assert chains[0].seed_question

# --- test_bank_cache.py ---

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.corpus.bank_cache import (
    bank_slug,
    is_fresh,
    list_banks,
    load_bank_bundle,
    load_question_bank,
    meta_path,
    question_bank_path,
    save_bank_artifacts,
    write_meta,
)
from scripts.corpus.export_bank import build_question_bank, render_frequency_report
from scripts.models import Question, RawPost
from scripts.corpus.store import save_raw_posts


def test_bank_slug_stable():
    a = bank_slug("AI 应用开发", ["字节跳动", "美团"])
    b = bank_slug("AI 应用开发", ["美团", "字节跳动"])
    assert a == b
    assert "AI" in a or "应用" in a


def test_is_fresh_respects_ttl(tmp_path: Path):
    slug = bank_slug("后端", [])
    write_meta(
        tmp_path,
        slug,
        role="后端",
        companies=[],
        post_count=1,
        question_count=2,
        sources={},
    )
    meta = json.loads(meta_path(tmp_path, slug).read_text(encoding="utf-8"))
    meta["updated_at"] = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    meta_path(tmp_path, slug).write_text(json.dumps(meta), encoding="utf-8")
    assert is_fresh(tmp_path, slug, ttl_days=7, today=date.today())

    meta["updated_at"] = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
    meta_path(tmp_path, slug).write_text(json.dumps(meta), encoding="utf-8")
    assert not is_fresh(tmp_path, slug, ttl_days=7, today=date.today())


def test_save_and_paths(tmp_path: Path):
    slug = bank_slug("Agent", ["字节跳动"])
    posts = [
        RawPost(
            source="x",
            url="u",
            post_type="text",
            raw_text="1. Agent 记忆怎么设计？",
            company="字节跳动",
        )
    ]
    save_raw_posts(posts, tmp_path / slug / "raw_posts.json")
    assert (tmp_path / slug / "raw_posts.json").is_file()
    write_meta(
        tmp_path,
        slug,
        role="Agent",
        companies=["字节跳动"],
        post_count=1,
        question_count=1,
        sources={},
    )
    assert question_bank_path(tmp_path, slug).parent.is_dir()


def test_list_and_load_bank_bundle(tmp_path: Path):
    slug = bank_slug("AI 应用开发", [])
    ranked = [
        Question(
            "RAG 怎么优化？",
            source_refs=["https://example.com/1"],
            freq=2,
            topic="RAG",
            company_tags=["字节跳动"],
        )
    ]
    bank = build_question_bank(
        role="AI 应用开发",
        companies=[],
        ranked=ranked,
        post_count=3,
        sources_meta={"demo": True},
    )
    report = render_frequency_report(bank)
    posts = [
        RawPost(
            source="nowcoder",
            url="https://example.com/1",
            post_type="text",
            raw_text="字节 RAG 面经\n1. 怎么优化？",
            company="字节跳动",
            role="AI 应用开发",
        )
    ]
    save_bank_artifacts(tmp_path, slug, posts, ranked, bank, report)
    write_meta(
        tmp_path,
        slug,
        role="AI 应用开发",
        companies=[],
        post_count=3,
        question_count=1,
        sources={"demo": True},
    )
    listed = list_banks(tmp_path)
    assert len(listed) == 1
    assert listed[0]["slug"] == slug
    bundle = load_bank_bundle(tmp_path, slug)
    assert bundle is not None
    assert bundle["bank"]["question_count"] == 1
    assert len(bundle["posts"]) == 1
    assert bundle["companies"][0]["name"] == "字节跳动"
    assert "RAG" in bundle["frequency_report"]
    assert load_question_bank(tmp_path, slug)["role"] == "AI 应用开发"
    assert load_bank_bundle(tmp_path, "missing") is None

# --- test_merged_role_bundle.py ---

from pathlib import Path

from scripts.corpus.bank_cache import load_merged_role_bundle


def test_load_merged_role_bundle_combines_ai_app_banks(tmp_path):
    root = Path(__file__).resolve().parents[1] / "corpus_cache" / "banks"
    if not root.is_dir():
        return
    bundle = load_merged_role_bundle(root, "AI 应用开发", role_id="ai_app")
    assert bundle is not None
    assert len(bundle["posts"]) >= 8
    assert len(bundle.get("merged_slugs") or []) >= 2
    with_img = sum(1 for p in bundle["posts"] if p.get("has_images") or p.get("image_urls"))
    assert with_img >= 5

# --- test_question_bank_view.py ---

from scripts.corpus.ai_gate import cluster_questions, enrich_answers
from scripts.corpus.question_bank_view import enrich_question_row, serialize_question_bank_ui


def test_serialize_question_bank_ui_topics_and_sources():
    bank = {
        "role": "数据开发",
        "post_count": 2,
        "recency_window_days": 90,
        "questions": [
            {
                "rank": 1,
                "cluster_id": "c001",
                "text": "Spark shuffle 原理？",
                "batch_count": 3,
                "topic": "Spark/计算",
                "confidence": "高频",
                "company_tags": ["字节跳动"],
                "role_tags": ["数据开发"],
                "variants": [],
                "source_refs": [
                    "https://www.xiaohongshu.com/explore/a",
                    "https://www.nowcoder.com/discuss/1",
                ],
            },
            {
                "rank": 2,
                "cluster_id": "c002",
                "text": "Hive 分区设计",
                "batch_count": 1,
                "topic": "Hive/SQL",
                "company_tags": [],
                "role_tags": [],
                "variants": [],
                "source_refs": ["https://www.nowcoder.com/discuss/2"],
            },
        ],
    }
    posts = [
        {
            "url": "https://www.xiaohongshu.com/explore/a",
            "source_url": "https://www.xiaohongshu.com/explore/a",
            "source": "xiaohongshu",
            "title": "字节数开面经",
            "company_label": "字节跳动",
        }
    ]
    ui = serialize_question_bank_ui(bank, posts)
    assert ui["stats"]["total"] == 2
    assert ui["stats"]["high"] == 1
    topic_names = {t["name"] for t in ui["topics"]}
    assert "Spark/计算" in topic_names
    assert "Hive/SQL" in topic_names
    q1 = ui["questions"][0]
    assert "小红书" in q1["source_labels"]
    assert q1["related_posts"][0]["title"] == "字节数开面经"


def test_enrich_question_row_confidence_default():
    row = enrich_question_row({"text": "test", "batch_count": 2})
    assert row["confidence"] == "中频"


def test_agent_cluster_merges_variants(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")
    qs = [
        Question(text="Spark shuffle 过程？", freq=2, topic="Spark/计算"),
        Question(text="Spark 的 shuffle 原理是什么？", freq=1, topic="Spark/计算"),
        Question(text="请做个自我介绍", freq=1),
    ]

    def fake(system, user, **_):
        if "参考" in system or "answers" in user:
            return {"answers": [{"id": "0", "answer": "要点1"}]}
        return {
            "groups": [{"canonical": "Spark shuffle 原理？", "topic": "Spark/计算", "ids": ["0", "1"]}],
            "drop": ["2"],
        }

    monkeypatch.setattr("scripts.corpus.ai_gate.chat_json", fake)
    out = cluster_questions(qs)
    assert len(out) == 1
    assert out[0].freq == 3
    assert "shuffle" in out[0].text.lower()


def test_enrich_answers_attaches_text(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("POST_AI_FILTER", "1")
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", "/tmp/ir-test-cache")
    qs = [Question(text="Hive 分区表怎么设计？", freq=1, topic="Hive/SQL")]

    def fake(system, user, **_):
        return {"answers": [{"id": "0", "answer": "按天分区 + 生命周期"}]}

    monkeypatch.setattr("scripts.corpus.ai_gate.chat_json", fake)
    enrich_answers(qs, "数据开发", top_n=5)
    assert "分区" in qs[0].answer

# --- test_posts_view.py ---

from scripts.corpus.posts_view import company_options, post_title, serialize_posts
from scripts.models import RawPost


def test_post_title_first_line():
    post = RawPost(
        source="nowcoder",
        url="u",
        post_type="text",
        raw_text="字节 AI 应用开发一面面经\n\n1. RAG 怎么优化？",
        company="字节跳动",
    )
    assert "面经" in post_title(post)


def test_company_options_sorted():
    posts = [
        RawPost("n", "u1", "text", "a", company="字节跳动"),
        RawPost("n", "u2", "text", "b", company="字节跳动"),
        RawPost("n", "u3", "text", "c", company="美团"),
        RawPost("n", "u4", "text", "d"),
    ]
    opts = company_options(posts)
    assert opts[0]["name"] == "字节跳动"
    assert opts[0]["count"] == 2
    assert any(o["name"] == "未标注" for o in opts)


def test_serialize_posts_includes_preview():
    posts = [
        RawPost(
            source="xiaohongshu",
            url="https://xhs/1",
            post_type="text",
            raw_text="标题面经\n正文很长" * 5,
            posted_at="2026-05-01",
            company="腾讯",
            role="AI 应用开发",
        )
    ]
    rows = serialize_posts(posts)
    assert len(rows) == 1
    assert rows[0]["title"]
    assert rows[0]["preview"]
    assert rows[0]["company_label"] == "腾讯"

# --- test_post_format.py ---

from scripts.corpus.post_format import (
    clean_post_text,
    format_body_html,
    resolve_source_url,
)


def test_clean_removes_topic_hashtags():
    raw = "腾讯 ai 应用开发 一面\n#互联网大厂[话题]# #面试[话题]# #agent[话题]#\n1. 项目介绍"
    cleaned = clean_post_text(raw)
    assert "#" not in cleaned
    assert "互联网大厂" not in cleaned or "项目介绍" in cleaned
    assert "1. 项目介绍" in cleaned


def test_format_body_html_paragraphs():
    raw = "标题\n1. 第一点\n2. 第二点\n普通段落"
    html = format_body_html(raw, title="标题")
    assert html.count("<p") >= 3
    assert "bullet" in html


def test_resolve_nowcoder_broken_link():
    url, label = resolve_source_url(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/detail/12345",
        title="后端开发面经",
    )
    assert "search/all" in url
    assert label == "在牛客搜索"


def test_resolve_nowcoder_uuid_link():
    url, label = resolve_source_url(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/main/detail/f054aef412104109a1dfa85e273e6faf",
        title="后端开发面经",
    )
    assert "feed/main/detail" in url
    assert label == "在牛客查看"

# --- test_post_text_merge.py ---

from scripts.corpus.post_format import clean_post_text
from scripts.corpus.post_text_merge import merge_article_and_ocr, strip_ocr_page_markers
from scripts.models import RawPost


def test_strip_ocr_page_markers():
    text = "[图片 OCR 第 1 页]\n教育背景\n浙江大学"
    assert strip_ocr_page_markers(text) == "教育背景\n浙江大学"


def test_merge_article_and_ocr():
    merged = merge_article_and_ocr(
        "今年 AI 应用面经分享",
        "[图片 OCR 第 1 页]\n1. RAG 优化\n\n[图片 OCR 第 2 页]\n2. Agent 设计",
    )
    assert "今年 AI 应用面经分享" in merged
    assert "RAG 优化" in merged
    assert "[图片 OCR" not in merged


def test_clean_post_text_strips_ocr_labels():
    assert "[图片 OCR" not in clean_post_text("[图片 OCR 第 1 页]\n正文")


def test_post_article_text_prefers_locator():
    from scripts.corpus.post_text_merge import post_article_text

    post = RawPost(
        source="xiaohongshu",
        url="u",
        post_type="image",
        locator_text="帖子标题\n补充说明",
        raw_text="[图片 OCR 第 1 页]\nOCR内容",
        image_ocr_text="[图片 OCR 第 1 页]\nOCR内容",
    )
    assert post_article_text(post) == "帖子标题\n补充说明"

# --- test_store.py ---

from scripts.models import RawPost, Question
from scripts.corpus.store import (
    save_raw_posts, load_raw_posts, save_questions, load_questions,
)


def test_raw_posts_save_and_load(tmp_path):
    posts = [RawPost("github", "u1", "text", "Q1"), RawPost("github", "u2", "text", "Q2")]
    path = tmp_path / "raw.json"
    save_raw_posts(posts, path)
    assert load_raw_posts(path) == posts


def test_questions_save_and_load(tmp_path):
    qs = [Question("Q1", ["u1"]), Question("Q2", ["u2"], freq=3)]
    path = tmp_path / "q.json"
    save_questions(qs, path)
    assert load_questions(path) == qs

# --- test_models.py ---

from scripts.models import RawPost, Question, FollowUpChain


def test_rawpost_roundtrips_through_dict():
    post = RawPost(
        source="nowcoder",
        url="https://example.com/p1",
        post_type="text",
        raw_text="What is MCP?",
        asset_paths=[],
        comments=["see docs"],
        company="字节跳动",
        role="AI 应用开发",
    )
    assert RawPost.from_dict(post.to_dict()) == post


def test_question_roundtrips_through_dict():
    q = Question(
        text="What is MCP?",
        source_refs=["https://example.com/p1"],
        freq=2,
        role_tags=["agent"],
        company_tags=["字节跳动"],
        topic="protocols",
        modality_origin="text",
    )
    assert Question.from_dict(q.to_dict()) == q


def test_followupchain_roundtrips_through_dict():
    chain = FollowUpChain(
        seed_question="What is MCP?",
        resume_anchor="skill-driven project",
        followups=["How does your skill engine work?"],
        is_grounded=True,
    )
    assert FollowUpChain.from_dict(chain.to_dict()) == chain


def test_rawpost_has_optional_posted_at_defaulting_none():
    post = RawPost("github", "u1", "text", "Q1")
    assert post.posted_at is None
    dated = RawPost("nowcoder", "u2", "text", "Q2", posted_at="2025-09-01")
    assert RawPost.from_dict(dated.to_dict()) == dated
    assert dated.posted_at == "2025-09-01"


def test_rawpost_new_content_fields_default_from_raw_text():
    post = RawPost("xiaohongshu", "u1", "image", "图片正文")
    assert post.locator_text == "图片正文"
    assert post.content_text == "图片正文"
    assert post.image_ocr_text is None
    assert post.needs_vision_fallback is False
    assert post.extraction_quality == "text_only"


def test_rawpost_from_dict_accepts_legacy_cache_without_new_fields():
    post = RawPost.from_dict(
        {
            "source": "xiaohongshu",
            "url": "u1",
            "post_type": "image",
            "raw_text": "旧缓存正文",
            "asset_paths": [],
            "comments": [],
        }
    )
    assert post.locator_text == "旧缓存正文"
    assert post.content_text == "旧缓存正文"
    assert post.raw_text == "旧缓存正文"


def test_question_has_optional_latest_posted_at_defaulting_none():
    q = Question("Q1", ["u1"])
    assert q.latest_posted_at is None
    dated = Question("Q2", ["u2"], latest_posted_at="2025-09-01")
    assert Question.from_dict(dated.to_dict()) == dated

# --- test_ingest_fallback.py ---

from pathlib import Path

import pytest

from scripts.corpus.ingest_fallback import (
    build_ingest_failure_message,
    corpus_matches_role,
    ingest_attempted_live,
    resolve_role_aware_fallback,
    role_mismatch_warning,
)
from scripts.config import sample_posts_path
from scripts.models import RawPost
from scripts.service import RunConfig, ingest_posts


def test_corpus_matches_role_ai_app_from_queries():
    hints = ["AI 应用开发 面经", "字节跳动 AI 应用开发 面经"]
    assert corpus_matches_role("AI 应用开发", hints)
    assert corpus_matches_role("AI应用开发", hints)


def test_corpus_does_not_match_backend_for_ai_queries():
    hints = ["AI 应用开发 面经", "字节跳动 Agent开发 面经"]
    assert not corpus_matches_role("后端开发", hints)


def test_resolve_role_aware_fallback_skips_mismatched_report(tmp_path, monkeypatch):
    report = tmp_path / "scrape_smoke_report.json"
    report.write_text(
        '{"queries":["AI 应用开发 面经"],"posts":[{"source":"xiaohongshu","url":"u","post_type":"text","raw_text":"RAG Agent 项目","role":"Agent开发"}]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))

    assert resolve_role_aware_fallback("AI 应用开发") == report
    assert resolve_role_aware_fallback("后端开发") is None


def test_ingest_attempted_live_flags():
    assert ingest_attempted_live(RunConfig(role="x", discover_nowcoder=True))
    assert ingest_attempted_live(RunConfig(role="x", nowcoder_urls=["https://nowcoder.com/discuss/1"]))
    assert not ingest_attempted_live(
        RunConfig(role="x", raw_posts="a.json", discover_nowcoder=False),
    )


def test_ingest_no_silent_fallback_on_failed_live(tmp_path, monkeypatch):
    banks = tmp_path / "banks"
    report = tmp_path / "scrape_smoke_report.json"
    report.write_text(
        '{"queries":["AI 应用开发 面经"],"posts":[{"source":"xiaohongshu","url":"u","post_type":"text","raw_text":"RAG 项目","posted_at":"2026-05-01"}]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))

    config = RunConfig(
        role="后端开发",
        cache_dir=str(banks),
        refresh=True,
        discover_nowcoder=True,
        discover_max_per_query=1,
        xhs_use_export=False,
    )

    monkeypatch.setattr(
        "scripts.service.discover_nowcoder_urls",
        lambda queries, **kwargs: ([], {"count": 0, "per_query": []}),
    )
    monkeypatch.setattr(
        "scripts.service.search_nowcoder_moments",
        lambda queries, **kwargs: ([], {"count": 0}),
    )

    with pytest.raises(FileNotFoundError, match="未抓到任何面经帖"):
        ingest_posts(config, ["后端开发 面经"])


def test_role_mismatch_warning_on_explicit_raw(tmp_path):
    raw = tmp_path / "demo.json"
    raw.write_text(
        '[{"source":"nowcoder","url":"u","post_type":"text","raw_text":"RAG","role":"AI 应用开发","posted_at":"2026-05-01"}]',
        encoding="utf-8",
    )
    msg = role_mismatch_warning("后端开发", raw)
    assert msg and "不匹配" in msg


def test_ingest_uses_role_matched_fallback_without_live(tmp_path, monkeypatch):
    banks = tmp_path / "banks"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INTERVIEWRADAR_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "scripts.service.discover_nowcoder_urls",
        lambda queries, **kwargs: ([], {"count": 0, "per_query": []}),
    )
    monkeypatch.setattr(
        "scripts.service.search_nowcoder_moments",
        lambda queries, **kwargs: ([], {"count": 0}),
    )

    config = RunConfig(
        role="AI 应用开发",
        cache_dir=str(banks),
        refresh=True,
        discover_nowcoder=False,
        xhs_use_export=False,
    )
    posts, meta, _ = ingest_posts(config, ["AI 应用开发 面经"])
    assert len(posts) >= 1
    assert meta["sources"].get("fallback") == str(sample_posts_path())


def test_build_ingest_failure_message_mentions_live():
    config = RunConfig(role="后端开发", discover_nowcoder=True)
    msg = build_ingest_failure_message("后端开发", config, ["后端开发 面经"])
    assert "不会自动改用" in msg
    assert "discover-nowcoder" in msg or "自动发现" in msg

# --- test_corpus_sync.py ---

from pathlib import Path

import yaml

from scripts.corpus.company_normalize import (
    normalize_company_name,
    reload_company_aliases_cache,
)
from scripts.corpus.tech_roles import parse_role_ids
from scripts.scrape.keywords import merged_nowcoder_queries_for_roles


def test_custom_company_aliases_yaml(tmp_path, monkeypatch):
    yaml_path = tmp_path / "aliases.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "subsidiaries": {"示例子公司": "示例集团"},
                "not_companies": ["badtag"],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_ALIASES_PATH", str(yaml_path))
    reload_company_aliases_cache()
    try:
        assert normalize_company_name("示例子公司") == "示例集团"
        assert normalize_company_name("badtag") is None
        assert normalize_company_name("淘天") == "阿里巴巴"
    finally:
        # Undo the env override before rebuilding the cache, or the custom
        # yaml poisons every alias test that runs after this one.
        monkeypatch.delenv("COMPANY_ALIASES_PATH", raising=False)
        reload_company_aliases_cache()


def test_parse_role_ids_dedupes_and_aliases():
    assert parse_role_ids("ai_app", "") == ["ai_app"]
    assert parse_role_ids("", "backend,ai_app,backend") == ["backend", "ai_app"]
    assert parse_role_ids("", "agent,backend") == ["ai_app", "backend"]
    assert parse_role_ids("", "") == ["data", "ai_app"]


def test_merged_queries_cover_multiple_roles():
    companies = ["字节跳动", "腾讯"]
    queries = merged_nowcoder_queries_for_roles(["ai_app", "backend"], companies)
    assert queries
    assert len(queries) >= len(companies) * 2

# --- test_company_catalog.py ---

from scripts.corpus.company_catalog import (
    INTERNET_GIANTS,
    MANUFACTURING_GIANTS,
    is_preset_company,
    list_company_groups,
)


def test_list_company_groups():
    groups = list_company_groups()
    assert len(groups) == 1
    assert groups[0]["id"] == "internet"
    assert "字节跳动" in groups[0]["companies"]
    assert "比亚迪" not in groups[0]["companies"]


def test_is_preset_company():
    assert is_preset_company("腾讯")
    assert is_preset_company("OPPO")
    assert is_preset_company("Shein")
    assert is_preset_company("Shopee")
    assert not is_preset_company("蔚来")
    assert not is_preset_company("某未知公司")

# --- test_company_normalize.py ---

from scripts.corpus.company_normalize import infer_company_from_text_normalized, normalize_company_name


def test_taotian_to_alibaba():
    assert normalize_company_name("淘天") == "阿里巴巴"
    assert normalize_company_name("淘天集团") == "阿里巴巴"


def test_ant_and_qwen_to_alibaba():
    assert normalize_company_name("蚂蚁") == "阿里巴巴"
    assert normalize_company_name("蚂蚁集团") == "阿里巴巴"
    assert normalize_company_name("通义千问") == "阿里巴巴"


def test_tencent_business_units():
    assert normalize_company_name("WXG") == "腾讯"
    assert normalize_company_name("csig") == "腾讯"


def test_bytedance_subsidiaries():
    assert normalize_company_name("TikTok") == "字节跳动"
    assert normalize_company_name("抖音") == "字节跳动"


def test_internet_giants_aliases():
    assert normalize_company_name("虾皮") == "Shopee"
    assert normalize_company_name("shein") == "Shein"
    assert normalize_company_name("oppo") == "OPPO"


def test_rejects_non_company_tags():
    assert normalize_company_name("AI") is None
    assert normalize_company_name("Ai") is None
    assert normalize_company_name("agent") is None
    assert normalize_company_name("27实习") is None
    assert normalize_company_name("双非") is None
    assert normalize_company_name("27") is None


def test_infer_from_text():
    assert infer_company_from_text_normalized("淘天 AI 应用开发一面") == "阿里巴巴"
    assert infer_company_from_text_normalized("WXG 后台开发二面") == "腾讯"

# --- test_interview_link.py ---

from scripts.jobs.interview_link import match_posts_to_job
from scripts.jobs.models import JobPosting
from scripts.models import RawPost


def test_match_posts_to_job_by_company_and_title():
    job = JobPosting(
        source="job_pro",
        source_id="1",
        url="https://jobs.example/1",
        title="AI应用开发工程师",
        company="字节跳动",
    )
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/main/detail/abc",
        post_type="text",
        raw_text="字节跳动 AI应用开发 一面 项目拷打",
        company="字节跳动",
    )
    matched = match_posts_to_job(job, [post])
    assert len(matched) == 1


def test_match_posts_to_job_different_company():
    job = JobPosting(
        source="job_pro",
        source_id="2",
        url="https://jobs.example/2",
        title="后端开发",
        company="腾讯",
    )
    post = RawPost(
        source="nowcoder",
        url="https://www.nowcoder.com/feed/main/detail/def",
        post_type="text",
        raw_text="字节跳动 后端 面经",
        company="字节跳动",
    )
    assert match_posts_to_job(job, [post]) == []
