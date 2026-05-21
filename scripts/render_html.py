"""Render the collected items into a single self-contained HTML page.

Design language: editorial, magazine-like (inspired by Linear changelog,
Vercel blog, Stripe Press). Mono-spaced metadata, generous whitespace,
sticky section nav, tasteful hairlines.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

CSS = """
:root {
  color-scheme: light dark;
  --bg: #fafaf7;
  --bg-elev: #ffffff;
  --ink: #111111;
  --ink-2: #5b5b5b;
  --ink-3: #8a8a8a;
  --rule: rgba(0,0,0,0.08);
  --accent: #ff5a1f;
  --tag-bg: rgba(0,0,0,0.04);
  --serif: "Iowan Old Style", "Apple Garamond", "Baskerville", "Times New Roman", serif;
  --sans: -apple-system, BlinkMacSystemFont, "Inter", "Helvetica Neue", Arial, sans-serif;
  --mono: "SF Mono", ui-monospace, "JetBrains Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e0e0c;
    --bg-elev: #16161420;
    --ink: #f4f1ea;
    --ink-2: #b8b4a9;
    --ink-3: #7a766c;
    --rule: rgba(255,255,255,0.10);
    --accent: #ff7a45;
    --tag-bg: rgba(255,255,255,0.06);
  }
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
a { color: inherit; }

/* --- Hero top row (title + GitHub links) --- */
.hero .gh {
  display: flex; align-items: center; gap: 8px;
  flex-shrink: 0;
  padding-top: 12px;
}
.hero .gh a {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--rule);
  border-radius: 999px;
  text-decoration: none;
  color: var(--ink);
  font-size: 12px; font-weight: 500;
  background: var(--bg-elev);
  transition: border-color .15s ease, transform .15s ease;
}
.hero .gh a:hover { border-color: var(--accent); transform: translateY(-1px); }
.hero .gh a svg { width: 14px; height: 14px; }
.hero .gh a.primary { background: var(--ink); color: var(--bg); border-color: var(--ink); }
.hero .gh a.primary:hover { background: var(--accent); border-color: var(--accent); color: #fff; }

@media (max-width: 720px) {
  .hero .gh { padding-top: 8px; }
}

/* --- Hero --- */
.hero {
  max-width: 1180px; margin: 0 auto;
  padding: 48px 32px;
}
.hero-top {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 24px; flex-wrap: wrap;
}
.hero h1 {
  font-family: var(--serif);
  font-weight: 500;
  font-size: clamp(48px, 7vw, 92px);
  line-height: 1.02;
  letter-spacing: -0.02em;
  margin: 0 0 24px;
}
.hero h1 em { font-style: italic; color: var(--accent); }
.hero p.lede {
  font-family: var(--serif);
  font-size: clamp(18px, 1.6vw, 22px);
  line-height: 1.45;
  color: var(--ink-2);
  max-width: 640px;
  margin: 0;
}
.rangebar-wrap {
  max-width: 1180px; margin: 0 auto;
  padding: 24px 32px 0;
  border-top: 1px solid var(--rule);
}
.rangebar {
  display: flex; flex-wrap: wrap; gap: 8px;
}
.rangebar button {
  appearance: none;
  border: 1px solid var(--rule);
  background: var(--tag-bg);
  color: var(--ink-2);
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 8px 11px;
  border-radius: 4px;
  cursor: pointer;
}
.rangebar button:hover {
  color: var(--ink);
  border-color: var(--accent);
}
.rangebar button.active {
  color: var(--bg);
  background: var(--accent);
  border-color: var(--accent);
}
.rangebar .range-status {
  align-self: center;
  margin-left: 6px;
  color: var(--ink-3);
  font-family: var(--mono);
  font-size: 11px;
}

/* --- Layout --- */
.shell {
  max-width: 1180px; margin: 0 auto;
  padding: 56px 32px 96px;
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 64px;
}
@media (max-width: 880px) {
  .shell { grid-template-columns: 1fr; gap: 32px; padding: 40px 24px 64px; }
  .sidenav { position: static !important; }
}
@media (max-width: 720px) {
  .hero { padding: 32px 20px; }
  .rangebar-wrap { padding: 20px 20px 0; }
}

.sidenav {
  position: sticky; top: 24px; align-self: start;
  font-family: var(--sans); font-size: 13px;
}
.sidenav .label {
  color: var(--ink-3); margin-bottom: 12px;
  font-family: var(--mono); font-size: 11px;
  letter-spacing: 0.06em; text-transform: uppercase;
}
.sidenav ol {
  list-style: none; padding: 0; margin: 0;
  border-left: 1px solid var(--rule);
}
.sidenav a {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 8px 14px;
  color: var(--ink-2); text-decoration: none;
  border-left: 1px solid transparent; margin-left: -1px;
  transition: color .15s ease, border-color .15s ease;
}
.sidenav a:hover { color: var(--ink); border-left-color: var(--accent); }
.sidenav a .n { color: var(--ink-3); font-family: var(--mono); font-size: 11px; }

/* --- Section --- */
section + section { margin-top: 88px; }
section header.s-head {
  display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 12px; margin-bottom: 28px;
}
section header.s-head h2 {
  font-family: var(--serif);
  font-weight: 500;
  font-size: 32px;
  letter-spacing: -0.01em;
  margin: 0;
}
section header.s-head .count {
  font-family: var(--mono); font-size: 12px;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3);
}

/* --- Cards --- */
.feed {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1px;
  background: var(--rule);
  border: 1px solid var(--rule);
  border-radius: 4px;
  overflow: hidden;
}
.entry {
  background: var(--bg);
  padding: 24px 22px 20px;
  display: flex; flex-direction: column;
  transition: background .2s ease;
}
.entry:hover { background: var(--bg-elev); }

.entry .row {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 14px;
}
.avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--ink); color: var(--bg);
  font-family: var(--mono); font-size: 11px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  letter-spacing: 0;
}
.who { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.who .name {
  font-weight: 600; font-size: 14px; line-height: 1.2;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.who .role {
  color: var(--ink-3); font-size: 12px; line-height: 1.3;
  font-family: var(--mono); letter-spacing: 0.02em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.tag {
  font-family: var(--mono);
  font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--ink-2); background: var(--tag-bg);
  padding: 3px 8px; border-radius: 3px;
  flex-shrink: 0;
}

.entry .title {
  font-family: var(--serif);
  font-size: 19px; line-height: 1.3;
  font-weight: 500; letter-spacing: -0.005em;
  margin: 2px 0 10px;
  color: var(--ink);
}
.entry .summary {
  color: var(--ink-2); font-size: 14px; line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}
.entry .summary :where(img, video, iframe) { display: none; }
.entry .foot {
  margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--rule);
  display: flex; align-items: center; justify-content: space-between;
  font-family: var(--mono); font-size: 11px;
  color: var(--ink-3); letter-spacing: 0.02em;
}
.entry .open {
  color: var(--accent); text-decoration: none; font-weight: 500;
}
.entry .open:hover { text-decoration: underline; text-underline-offset: 3px; }

.empty {
  grid-column: 1 / -1;
  text-align: center; color: var(--ink-3);
  padding: 48px 24px;
  font-family: var(--mono); font-size: 13px;
  letter-spacing: 0.04em; text-transform: uppercase;
  background: var(--bg);
}

footer.page-foot {
  display: none;
}
"""

CLIENT_JS = r"""
<script>
(function () {
  const ranges = [
    { id: "3h", label: "3h", hours: 3 },
    { id: "6h", label: "6h", hours: 6 },
    { id: "12h", label: "12h", hours: 12 },
    { id: "24h", label: "24h", hours: 24 },
    { id: "3d", label: "3d", hours: 72 },
    { id: "7d", label: "7d", hours: 168 }
  ];
  const kinds = [
    ["posts", "Posts", "x"],
    ["blogs", "Blogs & Long-form", "blogs"],
    ["podcasts", "Podcasts", "podcasts"],
    ["releases", "Trending Repos", "releases"],
    ["videos", "YouTube", "videos"]
  ];
  let archiveItems = [];
  let latestEnd = null;
  const cacheKey = document.querySelector('meta[name="digest-generated"]')?.content || String(Date.now());

  function withCacheKey(path) {
    const glue = path.includes("?") ? "&" : "?";
    return path + glue + "v=" + encodeURIComponent(cacheKey);
  }

  function text(value) {
    return String(value || "");
  }

  function escapeHtml(value) {
    return text(value).replace(/[&<>"']/g, function (ch) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch];
    });
  }

  function stripHtml(value) {
    const el = document.createElement("div");
    el.innerHTML = text(value);
    return el.textContent || el.innerText || "";
  }

  function initials(name) {
    const parts = text(name).trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function fmtTime(value) {
    if (!value) return "";
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    return dt.toISOString().replace("T", " ").replace(".000Z", " UTC").replace("Z", " UTC");
  }

  function tag(kind) {
    return {x: "Post", blogs: "Blog", podcasts: "Podcast", releases: "Trending", videos: "Video"}[kind] || "Item";
  }

  function card(item) {
    const name = item.source_name || item.author || "Unknown";
    const role = item.kind === "x" && item.source_handle
      ? "@" + item.source_handle + " · " + text(item.source_role)
      : text(item.source_role);
    const title = stripHtml(item.title);
    const summary = stripHtml(item.summary);
    const link = text(item.link);
    const titleBlock = item.kind !== "x" && title
      ? `<div class="title">${escapeHtml(title)}</div>`
      : "";
    const openLink = link
      ? `<a class="open" href="${escapeHtml(link)}" target="_blank" rel="noreferrer noopener">Open ↗</a>`
      : "";
    return `<article class="entry">
  <div class="row">
    <div class="avatar">${escapeHtml(initials(name))}</div>
    <div class="who">
      <span class="name">${escapeHtml(name)}</span>
      <span class="role">${escapeHtml(role)}</span>
    </div>
    <span class="tag">${escapeHtml(tag(item.kind))}</span>
  </div>
  ${titleBlock}
  <div class="summary">${escapeHtml(summary)}</div>
  <div class="foot">
    <span class="when">${escapeHtml(fmtTime(item.published))}</span>
    ${openLink}
  </div>
</article>`;
  }

  function sortDesc(items) {
    return items.slice().sort((a, b) => new Date(b.published || 0) - new Date(a.published || 0));
  }

  function canonicalLink(value) {
    const raw = text(value).trim();
    if (!raw) return "";
    try {
      const url = new URL(raw, location.href);
      Array.from(url.searchParams.keys()).forEach((key) => {
        if (key.toLowerCase().startsWith("utm_")) url.searchParams.delete(key);
      });
      url.hash = "";
      url.pathname = url.pathname.replace(/\/+$/, "");
      return (url.origin + url.pathname + url.search).toLowerCase();
    } catch (err) {
      return raw.toLowerCase();
    }
  }

  function keyFor(item) {
    const link = canonicalLink(item.link);
    if (link) return link;
    return [item.source_handle || "", item.summary || "", item.published || ""].join("|");
  }

  function filtered(hours) {
    if (!archiveItems.length || !latestEnd) return null;
    const cutoff = latestEnd.getTime() - hours * 60 * 60 * 1000;
    const seen = new Set();
    return sortDesc(archiveItems.filter((item) => {
      const dt = new Date(item.published || 0);
      if (Number.isNaN(dt.getTime()) || dt.getTime() < cutoff || dt.getTime() > latestEnd.getTime()) {
        return false;
      }
      const key = keyFor(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }));
  }

  function renderRange(rangeId) {
    const range = ranges.find((r) => r.id === rangeId) || ranges[3];
    const items = filtered(range.hours);
    if (!items) return;
    document.querySelectorAll(".rangebar button").forEach((button) => {
      button.classList.toggle("active", button.dataset.range === range.id);
    });
    const byKind = {};
    kinds.forEach(([, , kind]) => { byKind[kind] = []; });
    items.forEach((item) => {
      if (byKind[item.kind]) byKind[item.kind].push(item);
    });
    const sections = kinds.map(([slug, title, kind]) => {
      const rows = byKind[kind] || [];
      const body = rows.length
        ? `<div class="feed">${rows.map(card).join("")}</div>`
        : '<div class="feed"><div class="empty">No fresh items in window</div></div>';
      return `<section id="${slug}"><header class="s-head"><h2>${escapeHtml(title)}</h2><span class="count">${String(rows.length).padStart(2, "0")} items</span></header>${body}</section>`;
    }).join("");
    document.querySelector("main").innerHTML = sections;
    document.querySelector(".sidenav ol").innerHTML = kinds.map(([slug, title, kind]) => {
      const rows = byKind[kind] || [];
      return `<li><a href="#${slug}"><span>${escapeHtml(title)}</span><span class="n">${String(rows.length).padStart(2, "0")}</span></a></li>`;
    }).join("");
    const status = document.querySelector(".range-status");
    if (status) status.textContent = "Loaded " + items.length + " items";
  }

  async function loadArchive() {
    const status = document.querySelector(".range-status");
    try {
      const indexResp = await fetch(withCacheKey("data/index.json"), { cache: "reload" });
      if (!indexResp.ok) throw new Error("missing index");
      const index = await indexResp.json();
      const segmentPaths = (index.segments || []).map((segment) => segment.path).slice(-56);
      const dailyPaths = (index.daily || []).map((day) => day.path).slice(-7);
      const archivePaths = Array.from(new Set(dailyPaths.concat(segmentPaths)));
      const payloads = await Promise.all(archivePaths.map(async (path) => {
        const resp = await fetch(withCacheKey(path), { cache: "reload" });
        if (!resp.ok) return null;
        return resp.json();
      }));
      archiveItems = [];
      payloads.filter(Boolean).forEach((payload) => {
        const items = payload.items || {};
        Object.entries({x: "x", blogs: "blogs", podcasts: "podcasts", releases: "releases", videos: "videos"}).forEach(([kind, key]) => {
          (items[key] || []).forEach((item) => archiveItems.push(Object.assign({}, item, {kind})));
        });
      });
      const endValues = (index.segments || []).map((segment) => new Date(segment.window_end || 0)).filter((dt) => !Number.isNaN(dt.getTime()));
      const itemValues = archiveItems.map((item) => new Date(item.published || 0)).filter((dt) => !Number.isNaN(dt.getTime()));
      latestEnd = endValues.length
        ? new Date(Math.max.apply(null, endValues))
        : (itemValues.length ? new Date(Math.max.apply(null, itemValues)) : new Date());
      if (status) status.textContent = "7d archive ready";
      renderRange("24h");
    } catch (err) {
      if (status) status.textContent = "Local archive unavailable";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".rangebar button").forEach((button) => {
      button.addEventListener("click", () => renderRange(button.dataset.range));
    });
    loadArchive();
  });
})();
</script>
"""


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text.strip()


def _fmt_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    if isinstance(dt, str):
        text = dt.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _card(item: dict) -> str:
    name = item.get("source_name") or item.get("author") or "Unknown"
    role = item.get("source_role", "")
    title = _strip_html(item.get("title", ""))
    summary = _strip_html(item.get("summary", ""))
    link = item.get("link", "")
    when = _fmt_time(item.get("published"))
    kind = item.get("kind", "")
    tag_label = {
        "x": "Post",
        "podcast": "Podcast",
        "blog": "Blog",
        "release": "Trending",
        "video": "Video",
    }.get(kind, kind.title() or "Item")

    if kind == "x" and item.get("source_handle"):
        role_text = f'@{html.escape(item["source_handle"])} · {html.escape(role)}'
    else:
        role_text = html.escape(role)

    open_link = (
        f'<a class="open" href="{html.escape(link)}" target="_blank" rel="noreferrer noopener">Open ↗</a>'
        if link else ""
    )

    title_block = (
        f'<div class="title">{html.escape(title)}</div>'
        if kind != "x" and title
        else ""
    )

    return f"""
<article class="entry">
  <div class="row">
    <div class="avatar">{html.escape(_initials(name))}</div>
    <div class="who">
      <span class="name">{html.escape(name)}</span>
      <span class="role">{role_text}</span>
    </div>
    <span class="tag">{tag_label}</span>
  </div>
  {title_block}
  <div class="summary">{html.escape(summary)}</div>
  <div class="foot">
    <span class="when">{html.escape(when)}</span>
    {open_link}
  </div>
</article>
""".strip()


def render(
    x_items: list[dict],
    podcast_items: list[dict],
    blog_items: list[dict] | None = None,
    release_items: list[dict] | None = None,
    video_items: list[dict] | None = None,
    site: dict | None = None,
    interactive: bool = False,
) -> str:
    blog_items = blog_items or []
    release_items = release_items or []
    video_items = video_items or []
    site = site or {}
    repo = site.get("repo", "")
    repo_url = site.get("repo_url", f"https://github.com/{repo}" if repo else "")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")  # used in meta tag

    sections_meta = [
        ("posts", "Posts", x_items),
        ("blogs", "Blogs & Long-form", blog_items),
        ("podcasts", "Podcasts", podcast_items),
        ("releases", "Trending Repos", release_items),
        ("videos", "YouTube", video_items),
    ]

    def _section(slug: str, title: str, items: list[dict]) -> str:
        if not items:
            body = '<div class="feed"><div class="empty">No fresh items in window</div></div>'
        else:
            body = '<div class="feed">' + "\n".join(_card(i) for i in items) + "</div>"
        return (
            f'<section id="{slug}">'
            f'<header class="s-head"><h2>{html.escape(title)}</h2>'
            f'<span class="count">{len(items):02d} items</span></header>'
            f"{body}</section>"
        )

    sections = "".join(_section(s, t, items) for s, t, items in sections_meta)

    nav_items = "".join(
        f'<li><a href="#{s}"><span>{html.escape(t)}</span><span class="n">{len(items):02d}</span></a></li>'
        for s, t, items in sections_meta
    )

    gh_block = ""
    if repo_url:
        gh_block = (
            '<span class="gh">'
            f'<a href="{html.escape(repo_url)}" target="_blank" rel="noreferrer noopener" aria-label="Star on GitHub">'
            '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">'
            '<path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/>'
            '</svg>Star</a>'
            f'<a class="primary" href="{html.escape(repo_url)}" target="_blank" rel="noreferrer noopener" aria-label="View on GitHub">'
            '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">'
            '<path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/>'
            '</svg>GitHub</a>'
            '</span>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="digest-generated" content="{html.escape(generated)}" />
<title>Firsthand AI Digest</title>
<style>{CSS}</style>
</head>
<body>
<header class="hero">
  <div class="hero-top">
    <h1><em>Firsthand</em> AI Digest</h1>
    {gh_block}
  </div>
  <p class="lede">Posts, blogs, podcasts, repos, and videos from the people building AI. Auto-curated straight from the source.</p>
</header>
<div class="rangebar-wrap">
  <div class="rangebar" aria-label="Time range">
    <button type="button" data-range="3h">3h</button>
    <button type="button" data-range="6h">6h</button>
    <button type="button" data-range="12h">12h</button>
    <button class="active" type="button" data-range="24h">24h</button>
    <button type="button" data-range="3d">3d</button>
    <button type="button" data-range="7d">7d</button>
    <span class="range-status">{'Loading 7d archive' if interactive else ''}</span>
  </div>
</div>
<div class="shell">
  <nav class="sidenav">
    <div class="label">Sections</div>
    <ol>{nav_items}</ol>
  </nav>
  <main>
    {sections}
  </main>
</div>
<footer class="page-foot"></footer>
{CLIENT_JS if interactive else ''}
</body>
</html>
"""
