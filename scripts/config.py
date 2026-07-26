"""Environment-backed paths for open-source / local installs."""
from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ (does not override existing vars)."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if val and val[0] in {"'", '"'} and val[-1] == val[0]:
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


def focus_role_ids() -> list[str]:
    """Active scrape/UI role ids (default: 数据开发/数仓 + Agent 开发)."""
    from scripts.corpus.tech_roles import canonical_role_id

    raw = os.environ.get("INTERVIEWRADAR_FOCUS_ROLE_IDS", "data,ai_app").strip()
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        rid = canonical_role_id(part.strip())
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out or ["data", "ai_app"]


def focus_role_ids_csv() -> str:
    return ",".join(focus_role_ids())


def bootstrap_env() -> None:
    """Load optional .env from repo root and current working directory."""
    for base in (_PKG_ROOT, Path.cwd()):
        _load_env_file(base / ".env")


def package_root() -> Path:
    return _PKG_ROOT


def project_env_path() -> Path:
    return package_root() / ".env"


def write_project_env(updates: dict[str, str | None]) -> Path:
    """Upsert selected keys into the project .env and mirror them into os.environ."""
    path = project_env_path()
    existing: list[str] = []
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            existing = []

    remaining = {k: v for k, v in updates.items()}
    out: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key not in updates:
            out.append(line)
            continue
        value = remaining.pop(key)
        if value is None:
            continue
        out.append(f"{key}={value}")

    for key, value in remaining.items():
        if value is not None:
            out.append(f"{key}={value}")

    text = "\n".join(out).rstrip()
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")

    for key, value in updates.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return path


def app_display_name() -> str:
    """Label shown in Cursor browser tabs / background usage attribution."""
    return (
        os.environ.get("INTERVIEWRADAR_DISPLAY_NAME")
        or os.environ.get("APP_DISPLAY_NAME")
        or "data_agent_adar"
    ).strip() or "data_agent_adar"


def cache_dir() -> Path:
    raw = os.environ.get("INTERVIEWRADAR_CACHE_DIR")
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else Path.cwd() / p
    for base in (Path.cwd(), package_root()):
        candidate = base / "corpus_cache"
        if candidate.is_dir():
            return candidate
    return package_root() / "corpus_cache"


def banks_dir() -> Path:
    return cache_dir() / "banks"


def jobs_dir() -> Path:
    return cache_dir() / "jobs"


def boss_zhipin_cookie() -> str:
    """Cookie string for Boss直聘 wapi (user-exported from browser)."""
    return (
        os.environ.get("BOSS_ZHIPIN_COOKIE")
        or os.environ.get("INTERVIEWRADAR_BOSS_COOKIE")
        or ""
    ).strip()


def boss_zhipin_cookie_configured() -> bool:
    return len(boss_zhipin_cookie()) > 20


def boss_cdp_port() -> int:
    raw = os.environ.get("BOSS_CDP_PORT", "9222").strip()
    try:
        return int(raw)
    except ValueError:
        return 9222


def boss_cdp_enabled() -> bool:
    """Explicit CDP mode or auto when CDP port is listening."""
    if os.environ.get("BOSS_CDP", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    from scripts.jobs.cdp_client import cdp_port_open

    return cdp_port_open(boss_cdp_port())


def xhs_cdp_port() -> int:
    """Dedicated CDP port for Xiaohongshu (avoid Boss 9222)."""
    raw = os.environ.get("XHS_CDP_PORT", "9233").strip()
    try:
        return int(raw)
    except ValueError:
        return 9233


def xhs_cdp_profile() -> Path:
    raw = os.environ.get("XHS_CDP_PROFILE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".interview-radar" / "xhs-chrome-profile"


def xhs_cdp_enabled() -> bool:
    """Use real Chrome CDP for XHS (anti-detection). Default on; set XHS_CDP=0 for Playwright."""
    raw = os.environ.get("XHS_CDP", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def xhs_fetch_detail() -> bool:
    """Opt-in: visit a few high-value 面经 notes for full body (higher risk).
    Default off — the search-stage data + OCR covers most posts safely."""
    raw = os.environ.get("XHS_FETCH_DETAIL", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def xhs_driver() -> str:
    """Preferred Xiaohongshu scrape driver: playwright first, Spider_XHS fallback."""
    raw = os.environ.get("XHS_DRIVER", "playwright").strip().lower()
    if raw in {"playwright", "browser"}:
        return "playwright"
    if raw in {"spider_xhs", "spider-xhs", "spider"}:
        return "spider_xhs"
    return "playwright"


def xhs_scrape_timeout_seconds() -> int:
    """MediaCrawler subprocess timeout per keyword batch (CDP runs can be slow)."""
    raw = os.environ.get("XHS_SCRAPE_TIMEOUT_SECONDS", "1800").strip()
    try:
        return max(300, min(7200, int(raw)))
    except ValueError:
        return 1800


def spider_xhs_home() -> Path:
    env = os.environ.get("SPIDER_XHS_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".spider_xhs"


def mediacrawler_home() -> Path:
    """Deprecated: kept for old export paths only."""
    env = os.environ.get("MEDIACRAWLER_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".mediacrawler"


def xhs_cookies_str() -> str:
    """Full Xiaohongshu cookie header for Spider_XHS API."""
    for key in ("XHS_COOKIES", "COOKIES", "INTERVIEWRADAR_XHS_COOKIES"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    from scripts.jobs.cdp_client import cdp_extract_cookies_string, cdp_port_open

    if xhs_cdp_enabled() and cdp_port_open(xhs_cdp_port()):
        live = cdp_extract_cookies_string(xhs_cdp_port())
        if live:
            return live
    ws = xhs_web_session()
    if ws:
        return f"web_session={ws}"
    return ""


def xhs_cookies_source() -> str:
    for key in ("XHS_COOKIES", "COOKIES", "INTERVIEWRADAR_XHS_COOKIES"):
        if os.environ.get(key, "").strip():
            return f"env:{key}"
    from scripts.jobs.cdp_client import cdp_extract_cookies_string, cdp_port_open

    if xhs_cdp_enabled() and cdp_port_open(xhs_cdp_port()):
        if cdp_extract_cookies_string(xhs_cdp_port()):
            return f"cdp:{xhs_cdp_port()}"
    for key in ("XHS_WEB_SESSION", "INTERVIEWRADAR_XHS_WEB_SESSION"):
        if os.environ.get(key, "").strip():
            return f"env:{key}"
    if _xhs_web_session_from_mediancrawler():
        return "mediacrawler:legacy"
    return "none"


def xhs_cookies_configured() -> bool:
    cookies = xhs_cookies_str()
    return len(cookies) > 30 and "web_session=" in cookies


def _xhs_web_session_from_mediancrawler() -> str:
    """Read web_session from ~/.mediacrawler when .env is unset."""
    import re

    config_path = mediacrawler_home() / "config" / "base_config.py"
    if not config_path.is_file():
        return ""
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if not line.startswith("COOKIES ="):
            continue
        match = re.search(r'web_session=([^"\']+)', line)
        if match:
            return match.group(1).strip()
    return ""


def xhs_web_session() -> str:
    """`web_session` cookie value for Xiaohongshu (paste from browser DevTools)."""
    for key in ("XHS_WEB_SESSION", "INTERVIEWRADAR_XHS_WEB_SESSION"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return _xhs_web_session_from_mediancrawler()


def xhs_web_session_source() -> str:
    """Where the active web_session came from: env, mediancrawler, or none."""
    for key in ("XHS_WEB_SESSION", "INTERVIEWRADAR_XHS_WEB_SESSION"):
        if os.environ.get(key, "").strip():
            return f"env:{key}"
    if _xhs_web_session_from_mediancrawler():
        return "mediacrawler:legacy"
    return "none"


def xhs_web_session_configured() -> bool:
    return xhs_cookies_configured()


def xhs_batch_pause_seconds() -> float:
    raw = os.environ.get("XHS_BATCH_PAUSE_SECONDS", "30").strip()
    try:
        return max(10.0, float(raw))
    except ValueError:
        return 30.0


def xhs_max_keywords_per_run() -> int:
    raw = os.environ.get("XHS_MAX_KEYWORDS_PER_RUN", "32").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 32


def xhs_daily_keywords_per_day() -> int:
    """Daily incremental scrape: XHS keywords per cron run (primary source)."""
    raw = os.environ.get("XHS_DAILY_KEYWORDS_PER_DAY", "24").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 24


def nowcoder_daily_queries_per_day() -> int:
    """Daily incremental: Nowcoder supplement (lower priority than XHS)."""
    raw = os.environ.get("NOWCODER_DAILY_QUERIES_PER_DAY", "16").strip()
    try:
        return max(0, min(50, int(raw)))
    except ValueError:
        return 16


def xhs_min_posts_skip_nowcoder() -> int:
    raw = os.environ.get("XHS_MIN_POSTS_SKIP_NOWCODER", "5").strip()
    try:
        return max(1, min(500, int(raw)))
    except ValueError:
        return 5


def xhs_export_max_age_days() -> int:
    raw = os.environ.get("XHS_EXPORT_MAX_AGE_DAYS", "90").strip()
    try:
        return max(7, min(730, int(raw)))
    except ValueError:
        return 90


def xhs_export_max_files() -> int:
    raw = os.environ.get("XHS_EXPORT_MAX_FILES", "120").strip()
    try:
        return max(5, min(500, int(raw)))
    except ValueError:
        return 120


def xhs_crawler_max_notes() -> int:
    """MediaCrawler CRAWLER_MAX_NOTES_COUNT (per keyword)."""
    raw = os.environ.get("XHS_CRAWLER_MAX_NOTES", "50").strip()
    try:
        return max(15, min(200, int(raw)))
    except ValueError:
        return 50


def xhs_crawler_max_sleep_sec() -> int:
    """MediaCrawler inter-request sleep (anti-detection)."""
    raw = os.environ.get("XHS_CRAWLER_MAX_SLEEP_SEC", "3").strip()
    try:
        return max(1, min(15, int(raw)))
    except ValueError:
        return 3


def full_scrape_recency_days() -> int:
    """面经时效窗口（默认近 3 个月）。"""
    raw = os.environ.get("FULL_SCRAPE_RECENCY_DAYS", "90").strip()
    try:
        return max(30, min(730, int(raw)))
    except ValueError:
        return 90


def job_recency_days() -> int:
    """官网/Boss 在招岗位发布日期窗口（默认近 3 个月）。"""
    raw = os.environ.get("JOB_RECENCY_DAYS", "90").strip()
    try:
        return max(14, min(365, int(raw)))
    except ValueError:
        return 90


def company_aliases_path() -> Path:
    """YAML config for subsidiary → parent company normalization."""
    raw = os.environ.get("COMPANY_ALIASES_PATH", "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else package_root() / p
    return package_root() / "config" / "company_aliases.yaml"


def deepseek_api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def deepseek_api_base() -> str:
    raw = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").strip()
    return raw.rstrip("/")


def deepseek_model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"


def deepseek_prep_model() -> str:
    """强模型做 prep（默认 v4-pro）；未配置则回退到通用模型。"""
    return (os.environ.get("DEEPSEEK_PREP_MODEL", "").strip()
            or os.environ.get("DEEPSEEK_MODEL", "").strip()
            or "deepseek-v4-pro")


def vision_api_key() -> str:
    """OpenAI-compatible vision-language provider key (Qwen-VL / GLM-4V / …)."""
    return os.environ.get("VISION_API_KEY", "").strip()


def vision_api_base() -> str:
    return os.environ.get("VISION_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode").strip().rstrip("/")


def vision_model() -> str:
    return os.environ.get("VISION_MODEL", "qwen-vl-plus").strip() or "qwen-vl-plus"


def deepseek_use_proxy() -> bool:
    """默认直连 DeepSeek；仅 DEEPSEEK_USE_PROXY=1 时使用系统 HTTP_PROXY。"""
    raw = os.environ.get("DEEPSEEK_USE_PROXY", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def post_ai_filter_enabled() -> bool:
    raw = os.environ.get("POST_AI_FILTER", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool(deepseek_api_key())


def post_ai_filter_max_chars() -> int:
    raw = os.environ.get("POST_AI_FILTER_MAX_CHARS", "900").strip()
    try:
        return max(200, min(4000, int(raw)))
    except ValueError:
        return 900


def sample_posts_path() -> Path:
    """Bundled demo corpus — works offline without scraping."""
    env = os.environ.get("INTERVIEWRADAR_SAMPLE_POSTS")
    if env:
        p = Path(env).expanduser()
        return p if p.is_absolute() else package_root() / p
    return package_root() / "examples" / "sample_raw_posts.json"


def sample_resume_path() -> Path:
    return package_root() / "examples" / "sample_resume.txt"


def list_ingest_fallback_candidates() -> list[Path]:
    """Local corpora that ingest may use when role matches (see ingest_fallback)."""
    out: list[Path] = []
    for candidate in (
        cache_dir() / "scrape_smoke_report.json",
        sample_posts_path(),
    ):
        if candidate.is_file():
            out.append(candidate)
    return out


def resolve_posts_fallback() -> Path | None:
    """First existing local corpus path (for status/doctor — not role-filtered)."""
    candidates = list_ingest_fallback_candidates()
    return candidates[0] if candidates else None


bootstrap_env()
