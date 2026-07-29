"""Clean and format interview post text for Web UI display."""
from __future__ import annotations

import html
import re
from urllib.parse import quote

_TOPIC_HASHTAG = re.compile(r"#[^\s#]+(?:\[话题\])?#?")
_PLAIN_HASHTAG = re.compile(r"(?<![#\w/])#[\w\u4e00-\u9fff]{2,}(?:\[话题\])?")
_NC_SUBJECT_LINK = re.compile(
    r"<a\s+[^>]*href=\"/subject/index/[^\"]+\"[^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG = re.compile(r"<[^>]+>")
_BULLET_LINE = re.compile(r"^\s*(\d+[\.\、\)）]|[\-•●▪]\s+|(\d+)、)")
_OCR_PAGE_LABEL = re.compile(r"\[图片 OCR 第\s*\d+\s*页\]\s*\n?", re.I)
_BROKEN_NC_MOMENT = re.compile(r"nowcoder\.com/feed/detail/\d+", re.I)
_HTTP_URL = re.compile(r"^https?://", re.I)

# 手机截图 OCR 常混入的界面噪音:状态栏、时间、导航、水印 —— 独占一行时丢弃。
_NOISE_TIME = re.compile(r"^\d{1,2}[:：]\d{2}\s*[A-Za-z%]{0,2}$")      # 15:49 / 11:51C
_NOISE_STATUSBAR = re.compile(r"^[\d\s]*\d\s*[GK]?\s*(?:\d|[GK%]|5G|4G|LTE|Wi-?Fi|全网通|中国\S{0,4})[\d\sGK%]*$", re.I)  # 05G 5G 77 / 100%
_NOISE_NAV = re.compile(r"^[\s<>〈〉‹›❮❯←→‹›·\.。、,，:：;；|/\\\-—_\d]{1,4}$")   # 孤立导航符/短标点
# 单字符图标 OCR(点赞/箭头/方块等),独占一行时丢弃
_NOISE_ICON = re.compile(r"^[凸凹口回目▢◇◆●○◎△▽☆★※✓✗×＋+♡♥❤👍←→↑↓⌂☰⋯…]$")
_NOISE_WATERMARK = re.compile(r"(面经笔顶|笔记灵感|点击查看|长按识别|扫码|@[\w一-鿿]{1,12}的小红书)")
_NOISE_EXACT = {"面经笔顶", "小红书", "关注", "分享", "点赞", "收藏", "评论", "返回"}


def _is_noise_line(line: str) -> bool:
    """判断一行是否为截图界面噪音(状态栏/时间/导航/水印),真内容不误伤。"""
    s = line.strip()
    if not s:
        return False
    if s in _NOISE_EXACT:
        return True
    if _NOISE_TIME.match(s) or _NOISE_NAV.match(s) or _NOISE_ICON.match(s):
        return True
    if len(s) <= 10 and _NOISE_STATUSBAR.match(s):
        return True
    return False


def clean_post_text(text: str) -> str:
    """Remove hashtags, HTML, OCR page labels, and noisy link fragments."""
    if not text:
        return ""
    t = _OCR_PAGE_LABEL.sub("", text)
    t = _NC_SUBJECT_LINK.sub("", t)
    t = _HTML_TAG.sub("", t)
    t = _TOPIC_HASHTAG.sub("", t)
    t = _PLAIN_HASHTAG.sub("", t)
    t = _NOISE_WATERMARK.sub("", t)
    lines = []
    for line in t.splitlines():
        line = line.strip()
        if not line:
            lines.append("")
            continue
        # drop lines that are only leftover tags / punctuation
        if re.fullmatch(r"[\s#，,、/|]+", line):
            continue
        # drop 手机截图界面噪音(状态栏 / 时间 / 导航 / 水印)
        if _is_noise_line(line):
            continue
        lines.append(line)
    # collapse 3+ blank lines to 1
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(line)
    return "\n".join(out).strip()


def strip_duplicate_title(title: str, body: str) -> str:
    """Remove title line repeated at body start (modal already shows title)."""
    title = (title or "").strip()
    body = (body or "").strip()
    if not title or not body:
        return body
    lines = body.splitlines()
    if not lines:
        return body
    first = lines[0].strip()
    if first == title or first.replace(" ", "") == title.replace(" ", ""):
        return "\n".join(lines[1:]).strip()
    return body


def split_body_lines(text: str) -> list[str]:
    """Split text into display lines; expand inline numbered items."""
    cleaned = clean_post_text(text)
    if not cleaned:
        return []
    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        # Split "1. foo 2. bar" into separate lines, but only when there's
        # non-digit content before the next number (avoids "10." → "1" + "0. …")
        # and the marker isn't a decimal like "3.5" (punct must not precede a digit).
        parts = re.split(r"(?<=[^\d])\s+(?=\d+[\.\、\)）](?!\d))", line)
        for part in parts:
            p = part.strip()
            if p:
                lines.append(p)
    return lines


def format_body_html(text: str, *, title: str = "") -> str:
    """Each line becomes a paragraph; numbered bullets get distinct blocks."""
    body = strip_duplicate_title(title, text)
    lines = split_body_lines(body if body else text)
    if not lines:
        return ""
    parts: list[str] = []
    for line in lines:
        if not line.strip():
            parts.append("<br>")
            continue
        escaped = html.escape(line.strip())
        cls = "post-line bullet" if _BULLET_LINE.match(line) else "post-line"
        parts.append(f'<p class="{cls}">{escaped}</p>')
    return "\n".join(parts)


def _xhs_note_id_from_url(url: str) -> str:
    """Extract note_id from XHS URL: /explore/<note_id> or /discovery/item/<note_id>."""
    import re
    m = re.search(r"/(?:explore|discovery/item)/([a-f0-9]{24})", url or "")
    return m.group(1) if m else ""


def _local_assets_for_xhs_note(url: str) -> list[str]:
    """Find downloaded XHS images in corpus_cache/xhs/assets/<note_id>/."""
    from pathlib import Path
    from scripts.config import package_root

    note_id = _xhs_note_id_from_url(url)
    if not note_id:
        return []
    found: list[str] = []
    for root in (Path.cwd(), package_root()):
        folder = root / "corpus_cache" / "xhs" / "assets" / note_id
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*")):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and path.is_file():
                try:
                    rel = path.relative_to(root)
                    found.append(str(rel).replace("\\", "/"))
                except ValueError:
                    continue
        if found:
            return found
    return []


def _local_assets_for_post_url(url: str) -> list[str]:
    """Find downloaded images in corpus_cache/assets/posts/<hash>/."""
    import hashlib
    from pathlib import Path

    from scripts.config import package_root

    link = (url or "").strip()
    if not link:
        return []
    key = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
    found: list[str] = []
    for root in (Path.cwd(), package_root()):
        folder = root / "corpus_cache" / "assets" / "posts" / key
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*")):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and path.is_file():
                rel = _resolve_local_asset_path(
                    str(Path("corpus_cache") / "assets" / "posts" / key / path.name)
                )
                if rel:
                    found.append(rel)
        if found:
            return found
    return []


def _image_ref_to_str(raw) -> str:
    """An image ref may be a URL string or a rich dict {src,alt,width,height}
    (from HTML img parsing). Pull the URL out; never str() a dict into a path."""
    if isinstance(raw, dict):
        raw = raw.get("src") or raw.get("url") or raw.get("path") or ""
    return str(raw or "").strip()


def collect_image_urls(post_dict: dict) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        u = str(raw).strip()
        if not u or u in seen:
            return
        seen.add(u)
        urls.append(u)

    post_url = str(post_dict.get("url") or "").strip()
    source = str(post_dict.get("source") or "").lower()

    # For XHS posts: prefer locally cached images over expiring CDN URLs
    if source == "xiaohongshu" and post_url:
        local = _local_assets_for_xhs_note(post_url)
        if local:
            for rel in local:
                _add(rel)
            return urls

    for raw in post_dict.get("asset_paths") or []:
        u = _image_ref_to_str(raw)
        if not u:
            continue
        if _HTTP_URL.match(u):
            _add(u)
        else:
            _add(_resolve_local_asset_path(u) or u)
    for raw in post_dict.get("image_urls") or []:
        u = _image_ref_to_str(raw)
        if _HTTP_URL.match(u):
            _add(u)
    if not urls and post_url:
        for rel in _local_assets_for_post_url(post_url):
            _add(rel)
    return urls


def _resolve_local_asset_path(path_str: str) -> str | None:
    """Return servable relative path under corpus_cache/assets when file exists."""
    from pathlib import Path

    from scripts.config import package_root

    raw = (path_str or "").strip()
    if not raw or _HTTP_URL.match(raw):
        return None
    # A malformed ref (e.g. a stringified dict, or a URL-like value) can make
    # Windows raise OSError/WinError when probed as a path — never let that crash.
    candidates: list[Path] = []
    try:
        p = Path(raw).expanduser()
        if p.is_file():
            candidates.append(p.resolve())
        for base in (Path.cwd(), package_root()):
            candidate = (base / raw).resolve()
            if candidate.is_file():
                candidates.append(candidate)
    except OSError:
        return None
    for resolved in candidates:
        for root in (Path.cwd().resolve(), package_root().resolve()):
            assets_root = (root / "corpus_cache" / "assets").resolve()
            try:
                rel = resolved.relative_to(assets_root)
            except ValueError:
                continue
            return str(Path("corpus_cache") / "assets" / rel).replace("\\", "/")
    return None


def resolve_source_url(
    *,
    source: str,
    url: str,
    title: str,
) -> tuple[str, str]:
    """Return (url, link_label) for「查看原文」."""
    src = (source or "").lower()
    link = (url or "").strip()
    if src == "nowcoder":
        if link and "/feed/main/detail/" in link and len(link.rsplit("/", 1)[-1]) >= 16:
            return link, "在牛客查看"
        if link and _BROKEN_NC_MOMENT.search(link):
            link = ""
        q = clean_post_text(title).replace(" ", "")[:60]
        if q:
            return f"https://www.nowcoder.com/search/all?query={quote(q)}", "在牛客搜索"
        return "https://www.nowcoder.com/search/all", "在牛客搜索"
    if link:
        return link, "查看原文"
    return "", ""
