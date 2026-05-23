"""Render the collected items into a single self-contained HTML page.

Design language: Apple News-style dense card grid with colour-coded
category stripes, unified sans-serif typography, and hover-expand cards.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f2f2f7;
  --surface: #ffffff;
  --surface-2: #f8f8fc;
  --ink: #1c1c1e;
  --ink-2: #636366;
  --ink-3: #aeaeb2;
  --border: rgba(0,0,0,0.06);
  --shadow: 0 2px 12px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.05);
  --shadow-hover: 0 20px 48px rgba(0,0,0,0.16), 0 4px 16px rgba(0,0,0,0.10);
  --blog: #1d4ed8;
  --pod:  #7c3aed;
  --vid:  #dc2626;
  --x:    #6b7280;
  --sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, monospace;
  --radius: 16px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #000000;
    --surface: #1c1c1e;
    --surface-2: #2c2c2e;
    --ink: #ffffff;
    --ink-2: #ebebf5cc;
    --ink-3: #ebebf599;
    --border: rgba(255,255,255,0.08);
    --shadow: 0 2px 12px rgba(0,0,0,0.4), 0 1px 3px rgba(0,0,0,0.3);
    --shadow-hover: 0 20px 48px rgba(0,0,0,0.65), 0 4px 16px rgba(0,0,0,0.45);
    --x: #9ca3af;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; text-decoration: none; }

/* --- Hero --- */
.hero {
  max-width: 1280px; margin: 0 auto;
  padding: 56px 24px 40px;
}
.hero h1 {
  font-family: var(--sans);
  font-weight: 700;
  font-size: clamp(40px, 5.5vw, 72px);
  line-height: 1.04;
  letter-spacing: -0.035em;
  margin-bottom: 16px;
}
.hero h1 em { font-style: normal; color: var(--blog); }
.hero .lede {
  font-family: var(--sans);
  font-size: 16px; line-height: 1.55;
  color: var(--ink-2); max-width: 500px; margin: 0;
}

/* --- Divider --- */
.hero-divider {
  max-width: 1280px; margin: 0 auto; padding: 0 24px;
}
.hero-divider hr { border: none; border-top: 1px solid var(--border); margin: 0; }

/* --- Filter bar --- */
.filter-bar {
  max-width: 1280px; margin: 0 auto;
  padding: 20px 24px 12px;
  display: flex; flex-direction: column;
  align-items: flex-start; gap: 10px;
}
.seg {
  display: flex; gap: 0;
  background: var(--surface-2);
  border-radius: 999px; padding: 3px;
  border: 1px solid var(--border);
}
.seg button {
  appearance: none; border: none; background: none;
  padding: 6px 18px; border-radius: 999px;
  font-size: 13px; font-weight: 500;
  color: var(--ink-2); cursor: pointer;
  transition: all .15s;
}
.seg button.active { background: var(--surface); color: var(--ink); box-shadow: 0 1px 4px rgba(0,0,0,0.08); }

.time-seg {
  display: flex; gap: 0;
  background: var(--surface-2); border-radius: 999px; padding: 3px;
  border: 1px solid var(--border);
}
.time-seg button {
  appearance: none; border: none; background: none;
  padding: 6px 14px; border-radius: 999px;
  font-size: 13px; font-weight: 500;
  color: var(--ink-2); cursor: pointer;
  transition: all .15s;
}
.time-seg button.active { background: var(--surface); color: var(--ink); box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
/* --- Layout --- */
.page { max-width: 1280px; margin: 0 auto; padding: 0 24px 80px; }
.section { margin-bottom: 56px; }
.section-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 20px; padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.section-head h2 { font-size: 22px; font-weight: 700; letter-spacing: -0.015em; }
.section-head .count {
  font-family: var(--mono); font-size: 12px; color: var(--ink-3);
  letter-spacing: 0.04em; text-transform: uppercase;
}

/* --- Card grid --- */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}
@media (min-width: 1100px) { .grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 780px)  { .grid { grid-template-columns: 1fr 1fr; gap: 14px; } }
@media (max-width: 520px)  { .grid { grid-template-columns: 1fr; } }

/* --- Card --- */
.card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  display: flex; flex-direction: column;
  transition: box-shadow .25s ease;
  cursor: pointer;
  position: relative; z-index: 1;
  height: 100%;
}
.card:hover {
  box-shadow: var(--shadow-hover);
  z-index: 10;
}

.card-stripe {
  height: 5px; flex-shrink: 0;
  border-radius: var(--radius) var(--radius) 0 0;
}
.stripe-blogs    { background: linear-gradient(90deg, #1d4ed8, #3b82f6); }
.stripe-podcasts { background: linear-gradient(90deg, #7c3aed, #a855f7); }
.stripe-videos   { background: linear-gradient(90deg, #dc2626, #f97316); }
.stripe-x        { background: linear-gradient(90deg, #9ca3af, #c4c4c8); }
@media (prefers-color-scheme: dark) {
  .stripe-x { background: linear-gradient(90deg, #6b7280, #9ca3af); }
}

.card-body { padding: 22px 22px 16px; flex: 1; display: flex; flex-direction: column; }

/* --- Avatar row --- */
.card-top { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.avatar {
  width: 38px; height: 38px; border-radius: 50%;
  background: var(--ink); color: var(--bg);
  font-family: var(--mono); font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.card-who { min-width: 0; flex: 1; }
.card-name {
  font-size: 14px; font-weight: 600; line-height: 1.2;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.card-role {
  font-size: 12px; color: var(--ink-3);
  font-family: var(--mono); letter-spacing: 0.02em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* --- Badge --- */
.card-badge {
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; padding: 3px 8px; border-radius: 4px;
  flex-shrink: 0; font-family: var(--mono);
}
.badge-blogs    { background: #eff6ff; color: #1d4ed8; }
.badge-podcasts { background: #f5f3ff; color: #7c3aed; }
.badge-videos   { background: #fef2f2; color: #dc2626; }
.badge-x        { background: #f3f4f6; color: #6b7280; }
@media (prefers-color-scheme: dark) {
  .badge-blogs    { background: #1e3a8a22; color: #93c5fd; }
  .badge-podcasts { background: #4c1d9522; color: #c4b5fd; }
  .badge-videos   { background: #7f1d1d22; color: #fca5a5; }
  .badge-x        { background: rgba(255,255,255,0.07); color: #9ca3af; }
}

/* --- Title (blogs/podcasts/videos only) --- */
.card-title {
  font-size: 16px; font-weight: 600; line-height: 1.3;
  margin-bottom: 10px; letter-spacing: -0.005em;
}

/* --- Summary --- */
.card-summary {
  font-size: 14px; color: var(--ink-2); line-height: 1.6;
  flex: 1;
  word-break: break-word; overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* --- Foot --- */
.card-foot {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--border);
}
.card-time { font-family: var(--mono); font-size: 11px; color: var(--ink-3); }
.card-link {
  font-size: 12px; font-weight: 600; color: var(--blog);
  display: flex; align-items: center; gap: 3px;
  transition: color .12s;
}
.card-link:hover { text-decoration: underline; text-underline-offset: 3px; }
.card-link-podcasts { color: var(--pod); }
.card-link-videos   { color: var(--vid); }
.card-link-x        { color: var(--x); }

/* --- Empty state --- */
.empty {
  grid-column: 1 / -1;
  text-align: center; color: var(--ink-3);
  padding: 48px 24px;
  font-family: var(--mono); font-size: 13px;
  letter-spacing: 0.04em; text-transform: uppercase;
  background: var(--surface);
  border-radius: var(--radius);
}

/* --- Responsive hero --- */
@media (max-width: 640px) {
  .hero { padding: 36px 20px 28px; }
  .hero-divider { padding: 0 20px; }
  .filter-bar { padding: 16px 20px 12px; }
  .page { padding: 0 20px 64px; }
}

footer.page-foot { display: none; }
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
    ["blogs",    "Blogs & Long-form", "blogs"],
    ["podcasts",  "Podcasts",         "podcasts"],
    ["videos",    "Videos",           "videos"],
    ["posts",     "Posts",            "x"]
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
    const pad = (n) => String(n).padStart(2, "0");
    let tz = "";
    try {
      const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(dt);
      const part = parts.find((p) => p.type === "timeZoneName");
      if (part && part.value) tz = " " + part.value;
    } catch (err) { /* ignore */ }
    return dt.getFullYear() + "-" + pad(dt.getMonth() + 1) + "-" + pad(dt.getDate()) + " " +
           pad(dt.getHours()) + ":" + pad(dt.getMinutes()) + ":" + pad(dt.getSeconds()) + tz;
  }

  function tag(kind) {
    return {x: "Post", blogs: "Blog", podcasts: "Podcast", videos: "Video"}[kind] || "Item";
  }

  function badgeClass(kind) {
    return "badge-" + ({x: "x", blogs: "blogs", podcasts: "podcasts", videos: "videos"}[kind] || "x");
  }

  function stripeClass(kind) {
    return "stripe-" + ({x: "x", blogs: "blogs", podcasts: "podcasts", videos: "videos"}[kind] || "x");
  }

  function linkClass(kind) {
    return "card-link-" + ({x: "x", blogs: "blogs", podcasts: "podcasts", videos: "videos"}[kind] || "x");
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
      ? `<div class="card-title">${escapeHtml(title)}</div>`
      : "";
    const label = tag(item.kind);
    const linkLabel = {Blog: "Read article ↗", Podcast: "Listen ↗", Video: "Watch ↗", Post: "Open ↗"}[label] || "Open ↗";
    const openHtml = link
      ? `<a class="card-link ${linkClass(item.kind)}" href="${escapeHtml(link)}" target="_blank" rel="noreferrer noopener">${linkLabel}</a>`
      : "";
    return `<article class="card">
  <div class="card-stripe ${stripeClass(item.kind)}"></div>
  <div class="card-body">
    <div class="card-top">
      <div class="avatar">${escapeHtml(initials(name))}</div>
      <div class="card-who">
        <div class="card-name">${escapeHtml(name)}</div>
        <div class="card-role">${escapeHtml(role)}</div>
      </div>
      <span class="card-badge ${badgeClass(item.kind)}">${escapeHtml(label)}</span>
    </div>
    ${titleBlock}
    <div class="card-summary">${escapeHtml(summary)}</div>
    <div class="card-foot">
      <span class="card-time" data-iso="${escapeHtml(text(item.published))}">${escapeHtml(fmtTime(item.published))}</span>
      ${openHtml}
    </div>
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
    const range = ranges.find((r) => r.id === rangeId) || ranges[4];
    const items = filtered(range.hours);
    if (!items) return;
    document.querySelectorAll(".time-seg button").forEach((button) => {
      button.classList.toggle("active", button.dataset.range === range.id);
    });
    const byKind = {};
    kinds.forEach(([, , kind]) => { byKind[kind] = []; });
    items.forEach((item) => {
      if (byKind[item.kind]) byKind[item.kind].push(item);
    });
    const sections = kinds.map(([slug, title, kind]) => {
      const rows = byKind[kind] || [];
      if (!rows.length) return "";
      return `<div class="section" id="${slug}"><div class="section-head"><h2>${escapeHtml(title)}</h2><span class="count">${String(rows.length).padStart(2, "0")} items</span></div><div class="grid">${rows.map(card).join("")}</div></div>`;
    }).join("");
    document.querySelector(".page").innerHTML = sections;
    document.querySelectorAll(".seg button").forEach(b => b.classList.remove("active"));
    const allBtn = document.querySelector(".seg button");
    if (allBtn) allBtn.classList.add("active");
  }

  async function loadArchive() {
    try {
      const indexResp = await fetch(withCacheKey("data/index.json"), { cache: "reload" });
      if (!indexResp.ok) throw new Error("missing index");
      const index = await indexResp.json();
      // Only fetch segments whose window_end is within the last 7d (168h).
      // This cuts the initial fetch from ~63 files down to ~28.
      const cutoff = new Date(Date.now() - 168 * 60 * 60 * 1000);
      const recentSegments = (index.segments || []).filter(function (s) {
        var t = new Date(s.window_end || 0);
        return !isNaN(t.getTime()) && t >= cutoff;
      });
      const segmentPaths = recentSegments.map(function (s) { return s.path; });
      const dailyPaths = (index.daily || []).map(function (d) { return d.path; }).slice(-7);
      const archivePaths = Array.from(new Set(dailyPaths.concat(segmentPaths)));
      if (!archivePaths.length) return;
      const payloads = await Promise.all(archivePaths.map(async function (path) {
        var resp = await fetch(withCacheKey(path), { cache: "reload" });
        if (!resp.ok) return null;
        return resp.json();
      }));
      archiveItems = [];
      payloads.filter(Boolean).forEach(function (payload) {
        var items = payload.items || {};
        Object.entries({x: "x", blogs: "blogs", podcasts: "podcasts", videos: "videos"}).forEach(function (entry) {
          var key = entry[0], kind = entry[1];
          (items[key] || []).forEach(function (item) { archiveItems.push(Object.assign({}, item, {kind: kind})); });
        });
      });
      var endValues = recentSegments.map(function (s) { return new Date(s.window_end || 0); }).filter(function (dt) { return !isNaN(dt.getTime()); });
      var itemValues = archiveItems.map(function (item) { return new Date(item.published || 0); }).filter(function (dt) { return !isNaN(dt.getTime()); });
      latestEnd = endValues.length
        ? new Date(Math.max.apply(null, endValues))
        : (itemValues.length ? new Date(Math.max.apply(null, itemValues)) : new Date());
      renderRange("3d");
    } catch (err) {
      // archive unavailable — showing server-rendered content only
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".time-seg button").forEach((button) => {
      button.addEventListener("click", () => renderRange(button.dataset.range));
    });
    document.querySelectorAll(".seg button").forEach((button) => {
      button.addEventListener("click", function () {
        document.querySelectorAll(".seg button").forEach(b => b.classList.remove("active"));
        this.classList.add("active");
        const kindLabel = this.textContent.trim();
        const mapping = {"Blogs": "blogs", "Podcasts": "podcasts", "Videos": "videos", "Posts": "posts"};
        const target = mapping[kindLabel];
        document.querySelectorAll(".section").forEach(s => {
          s.style.display = (!target || s.id === target) ? "" : "none";
        });
      });
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


def _coerce_utc(dt) -> datetime | None:
    if not dt:
        return None
    if isinstance(dt, str):
        text = dt.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_time(dt) -> str:
    coerced = _coerce_utc(dt)
    if not coerced:
        return ""
    return coerced.strftime("%Y-%m-%d %H:%M:%S UTC")


def _iso_time(dt) -> str:
    coerced = _coerce_utc(dt)
    if not coerced:
        return ""
    return coerced.isoformat()


def _card(item: dict) -> str:
    name = item.get("source_name") or item.get("author") or "Unknown"
    role = item.get("source_role", "")
    title = _strip_html(item.get("title", ""))
    summary = _strip_html(item.get("summary", ""))
    link = item.get("link", "")
    published = item.get("published")
    when = _fmt_time(published)
    iso = _iso_time(published)
    kind = item.get("kind", "")
    tag_label = {
        "x": "Post",
        "podcasts": "Podcast",
        "blogs": "Blog",
        "videos": "Video",
    }.get(kind, kind.title() or "Item")

    if kind == "x" and item.get("source_handle"):
        role_text = f'@{html.escape(item["source_handle"])} · {html.escape(role)}'
    else:
        role_text = html.escape(role)

    link_label = {
        "Blog": "Read article ↗",
        "Podcast": "Listen ↗",
        "Video": "Watch ↗",
        "Post": "Open ↗",
    }.get(tag_label, "Open ↗")

    open_link = (
        f'<a class="card-link card-link-{html.escape(kind)}" href="{html.escape(link)}" target="_blank" rel="noreferrer noopener">{link_label}</a>'
        if link else ""
    )

    title_block = (
        f'<div class="card-title">{html.escape(title)}</div>'
        if kind != "x" and title
        else ""
    )

    return f"""
<article class="card">
  <div class="card-stripe stripe-{html.escape(kind)}"></div>
  <div class="card-body">
    <div class="card-top">
      <div class="avatar">{html.escape(_initials(name))}</div>
      <div class="card-who">
        <div class="card-name">{html.escape(name)}</div>
        <div class="card-role">{role_text}</div>
      </div>
      <span class="card-badge badge-{html.escape(kind)}">{tag_label}</span>
    </div>
    {title_block}
    <div class="card-summary">{html.escape(summary)}</div>
    <div class="card-foot">
      <span class="card-time" data-iso="{html.escape(iso)}">{html.escape(when)}</span>
      {open_link}
    </div>
  </div>
</article>
""".strip()


def render(
    x_items: list[dict],
    podcast_items: list[dict],
    blog_items: list[dict] | None = None,
    video_items: list[dict] | None = None,
    site: dict | None = None,
    interactive: bool = False,
) -> str:
    blog_items = blog_items or []
    video_items = video_items or []
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")  # used in meta tag

    sections_meta = [
        ("blogs",    "Blogs & Long-form", blog_items),
        ("podcasts", "Podcasts",          podcast_items),
        ("videos",   "Videos",             video_items),
        ("posts",    "Posts",              x_items),
    ]

    def _section(slug: str, title: str, items: list[dict]) -> str:
        if not items:
            return ""
        body = '<div class="grid">' + "\n".join(_card(i) for i in items) + "</div>"
        return (
            f'<div class="section" id="{slug}">'
            f'<div class="section-head"><h2>{html.escape(title)}</h2>'
            f'<span class="count">{len(items):02d} items</span></div>'
            f"{body}</div>"
        )

    sections = "".join(_section(s, t, items) for s, t, items in sections_meta)

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
  <h1><em>Firsthand</em> AI Digest</h1>
  <p class="lede">Posts, blogs, podcasts and videos from the people building AI &mdash; straight from the source.</p>
</header>
<div class="hero-divider"><hr /></div>
<div class="filter-bar">
  <div class="time-seg" aria-label="Time range">
    <button type="button" data-range="3h">3h</button>
    <button type="button" data-range="6h">6h</button>
    <button type="button" data-range="12h">12h</button>
    <button type="button" data-range="24h">24h</button>
    <button class="active" type="button" data-range="3d">3d</button>
    <button type="button" data-range="7d">7d</button>
  </div>
  <div class="seg" aria-label="Content type">
    <button type="button" class="active">All</button>
    <button type="button">Blogs</button>
    <button type="button">Podcasts</button>
    <button type="button">Videos</button>
    <button type="button">Posts</button>
  </div>
</div>
<div class="page">
  {sections}
</div>
<footer class="page-foot"></footer>
<script>
(function () {{
  function fmtLocal(iso) {{
    if (!iso) return "";
    var dt = new Date(iso);
    if (isNaN(dt.getTime())) return "";
    var pad = function (n) {{ return String(n).padStart(2, "0"); }};
    var tz = "";
    try {{
      var parts = new Intl.DateTimeFormat(undefined, {{ timeZoneName: "short" }}).formatToParts(dt);
      var part = parts.find(function (p) {{ return p.type === "timeZoneName"; }});
      if (part && part.value) tz = " " + part.value;
    }} catch (e) {{ /* ignore */ }}
    return dt.getFullYear() + "-" + pad(dt.getMonth() + 1) + "-" + pad(dt.getDate()) + " " +
           pad(dt.getHours()) + ":" + pad(dt.getMinutes()) + ":" + pad(dt.getSeconds()) + tz;
  }}
  function apply(root) {{
    (root || document).querySelectorAll(".card-time[data-iso]").forEach(function (el) {{
      var out = fmtLocal(el.getAttribute("data-iso"));
      if (out) el.textContent = out;
    }});
  }}
  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", function () {{ apply(); }});
  }} else {{
    apply();
  }}
  window.__applyLocalTime = apply;
}})();
</script>
{CLIENT_JS if interactive else ''}
</body>
</html>
"""
