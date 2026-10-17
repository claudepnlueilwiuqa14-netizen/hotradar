#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hotradar.sources —— 全平台热榜采集适配器
每个适配器返回统一结构：
  [{"platform": str, "rank": int, "title": str, "url": str, "hot": int|None, "tag": str|None}]
抓不到的源返回 [] 并把原因写进 LAST_ERRORS（**不伪造数据**）。
"""
import json, gzip, io, re, time, urllib.request, urllib.error, urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TIMEOUT = 20
PROXY = "http://127.0.0.1:7897"   # 沙箱直连被透明代理拦，必须走 Clash

LAST_ERRORS = {}

# CDP 复用工具（2026-10-17 新增）：优先复用 Chrome 9222 里已停靠的标签页
try:
    from cdpkit import cdp_reuse, cdp_open, JS_LINKS
except Exception:      # 单独跑 sources.py 时目录已在 sys.path；失败就降级
    def cdp_reuse(*a, **k):
        return None

    def cdp_open(*a, **k):
        return None

    JS_LINKS = "() => []"


def _open(url, headers=None, timeout=TIMEOUT, proxy=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}
    if headers:
        h.update(headers)
    if proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request(url, headers=h)
    r = op.open(rq, timeout=timeout)
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return raw.decode("utf-8", "ignore")


def _get(url, headers=None, timeout=TIMEOUT, decode=True):
    """代理优先，失败自动换直连，两条路各重试。

    2026-10-17 实测：国内站走 Clash 代理会 SSL EOF / 403，直连反而通；
    国际站（github/hackernews）必须走代理。所以两条路都要试，谁通用谁。
    """
    last = None
    for px in (PROXY, None):
        for attempt in range(2):
            try:
                return _open(url, headers, timeout, px)
            except Exception as e:
                last = e
                time.sleep(0.6 * (attempt + 1))
    raise last


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(万|w|W|亿|k|K)?", s)
    if not m:
        return None
    n = float(m.group(1))
    u = (m.group(2) or "").lower()
    if u in ("万", "w"):
        n *= 10000
    elif u == "亿":
        n *= 100000000
    elif u == "k":
        n *= 1000
    return int(n)


def _ok(name):
    LAST_ERRORS.pop(name, None)


def _err(name, e):
    LAST_ERRORS[name] = str(e)[:200]


# ---------------------------------------------------------------- 微博热搜

# ---------------------------------------------------------------- 需登录态的源：CDP 接本机已登录 Chrome(9222)
CDP_URL = "http://127.0.0.1:9222"


def _cdp_pages():
    try:
        return json.loads(_get(CDP_URL + "/json/list", timeout=8))
    except Exception as e:
        return []


def cdp_fetch(url, wait_ms=2500, js=None):
    """用本机已登录 Chrome（CDP 9222）打开页面并取正文。没有 Chrome 时返回 None。"""
    pages = _cdp_pages()
    if not pages:
        return None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP_URL)
            ctx = b.contexts[0] if b.contexts else b.new_context()
            pg = ctx.new_page()
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(wait_ms)
            html = js if js else pg.content()
            pg.close()
            return html
    except Exception as e:
        _err("cdp", e)
        return None


def weibo():
    n = "微博"
    try:
        d = json.loads(_get("https://m.weibo.cn/api/container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26show_type%3D1"))
        cards = (d.get("data") or {}).get("cards") or []
        out = []
        for c in cards:
            for g in (c.get("card_group") or []):
                t = (g.get("desc") or "").strip()
                if not t:
                    continue
                out.append({"platform": n, "rank": len(out) + 1, "title": t,
                            "url": "https://s.weibo.cn/weibo?q=" + urllib.parse.quote("#%s#" % t),
                            "hot": _num(g.get("desc_extr")), "tag": (g.get("icon") or "")[:20] or None})
                if len(out) >= 50:
                    break
            if len(out) >= 50:
                break
        if out:
            _ok(n); return out
        _err(n, "解析到 0 条")
    except Exception as e:
        _err(n, e)
    # 兜底：桌面端 ajax
    try:
        d = json.loads(_get("https://weibo.com/ajax/side/hotSearch"))
        band = (d.get("data") or {}).get("realtime") or []
        out = []
        for i, b in enumerate(band):
            if not b.get("word"):
                continue
            out.append({"platform": n, "rank": i + 1, "title": b["word"],
                        "url": "https://s.weibo.cn/weibo?q=" + urllib.parse.quote("#%s#" % b["word"]),
                        "hot": b.get("num"), "tag": b.get("label_name")})
        if out:
            _ok(n); return out
    except Exception as e:
        _err(n, e)
    # 最后兜底：复用本机已登录 Chrome（CDP 9222）里停靠的 s.weibo.cn 标签页
    # 2026-10-17 实测：该页停靠后台时 DOM 是空的，必须先 reload 再取
    html = cdp_reuse("s.weibo.cn/top/summary", JS_LINKS, wait_ms=2500,
                     reload_first=True)
    if html:
        out = []
        for t, h in html:
            q = t.replace("#", "").strip()
            if len(q) < 3:
                continue
            out.append({"platform": n, "rank": len(out) + 1, "title": q,
                        "url": "https://s.weibo.cn/weibo?q=" + urllib.parse.quote("#%s#" % q),
                        "hot": None, "tag": None})
        if out:
            _ok(n); return out[:50]
        _err(n, "CDP 标签页打开成功但没解析到榜单（可能未登录或未渲染）")
    else:
        _err(n, "接口被反爬(403/访客系统)，且 CDP 9222 没有 s.weibo.cn 标签页 —— "
                "用带 --remote-debugging-port=9222 的 Chrome 登录微博后重试")
    return []


# ---------------------------------------------------------------- 百度热搜
def baidu():
    n = "百度"
    try:
        d = json.loads(_get("https://top.baidu.com/api/board?platform=wise&tab=realtime"))
        cards = ((d.get("data") or {}).get("cards")) or []
        out = []
        for c in cards:
            # 百度返回是两层嵌套：cards[].content[].content[]
            lvl1 = c.get("content") or []
            for b in lvl1:
                inner = b.get("content") if isinstance(b, dict) and isinstance(b.get("content"), list) else [b]
                for it in inner:
                    if not isinstance(it, dict) or not it.get("word"):
                        continue
                    out.append({"platform": n, "rank": len(out) + 1, "title": it["word"],
                                "url": it.get("url") or "https://www.baidu.com/s?wd=" + urllib.parse.quote(it["word"]),
                                "hot": _num(it.get("hotScore")),
                                "tag": ("置顶" if it.get("isTop") else it.get("hotTag")) or None})
                    if len(out) >= 50:
                        break
                if len(out) >= 50:
                    break
            if len(out) >= 50:
                break
        if out:
            _ok(n); return out
        _err(n, "0 条")
    except Exception as e:
        _err(n, e)
    return []


# ---------------------------------------------------------------- 今日头条
def toutiao():
    n = "头条"
    try:
        d = json.loads(_get("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"))
        arr = d.get("data") or []
        out = []
        for i, it in enumerate(arr):
            t = (it.get("Title") or "").strip()
            if not t:
                continue
            out.append({"platform": n, "rank": i + 1, "title": t,
                        "url": it.get("Url") or "",
                        "hot": _num(it.get("HotValue")), "tag": it.get("Label") or None})
        if out:
            _ok(n); return out
        _err(n, "0 条")
    except Exception as e:
        _err(n, e)
    return []


# ---------------------------------------------------------------- 知乎热榜
def zhihu():
    n = "知乎"
    for url in ("https://api.zhihu.com/topstory/hot-list?limit=50",
                "https://www.zhihu.com/api/v4/search/top_search"):
        try:
            d = json.loads(_get(url, {"Referer": "https://www.zhihu.com/"}))
            arr = d.get("data") or []
            out = []
            for i, it in enumerate(arr):
                if isinstance(it, dict) and isinstance(it.get("target"), dict):
                    tg = it["target"]
                    q = ((tg.get("title_area") or {}).get("text")) or tg.get("title") or ""
                    lid = tg.get("id")
                    hot = _num((tg.get("metrics_area") or {}).get("text"))
                else:
                    q = (it.get("query") or it.get("title") or "").strip()
                    lid = ""
                    hot = _num(it.get("display_detail") or it.get("hot_value"))
                if not q:
                    continue
                out.append({"platform": n, "rank": len(out) + 1, "title": q,
                            "url": "https://www.zhihu.com/question/" + str(lid) if lid else "https://www.zhihu.com/search?q=" + urllib.parse.quote(q),
                            "hot": hot, "tag": it.get("type") or None})
            if out:
                _ok(n); return out
        except Exception as e:
            _err(n, e)
    return []


# ---------------------------------------------------------------- B 站热门
def bilibili():
    n = "B站"
    try:
        d = json.loads(_get("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
                            {"Referer": "https://www.bilibili.com/"}))
        lst = (d.get("data") or {}).get("list") or []
        out = []
        for i, v in enumerate(lst):
            out.append({"platform": n, "rank": i + 1, "title": v.get("title"),
                        "url": v.get("short_link_v2") or ("https://www.bilibili.com/video/" + v.get("bvid", "")),
                        "hot": _num(v.get("stat", {}).get("view")),
                        "tag": v.get("tname") or None})
        if out:
            _ok(n); return out
        _err(n, "code=%s msg=%s" % (d.get("code"), d.get("message")))
    except Exception as e:
        _err(n, e)
    return []


# ---------------------------------------------------------------- 抖音热点
def douyin():
    n = "抖音"
    last = ""
    for attempt in range(3):
        try:
            d = json.loads(_get("https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383",
                                {"Referer": "https://www.douyin.com/hot"}))
            data = d.get("data") or {}
            # 双榜: word_list 热搜主榜 + trending_list 实时上升
            out = []
            for i, v in enumerate(data.get("word_list") or []):
                out.append({"platform": n, "rank": i + 1, "title": v.get("word"),
                            "url": "https://www.douyin.com/hot/" + str(v.get("sentence_id") or ""),
                            "hot": _num(v.get("hot_value")), "tag": v.get("label") or None})
            base = len(out)
            for j, v in enumerate(data.get("trending_list") or []):
                out.append({"platform": n + "-上升", "rank": base + j + 1, "title": v.get("word"),
                            "url": "https://www.douyin.com/hot/" + str(v.get("sentence_id") or ""),
                            "hot": _num(v.get("hot_value")), "tag": v.get("label") or None})
            if out:
                _ok(n); return out
            last = "status_code=%s keys=%s" % (d.get("status_code"), list(data.keys()))
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:
            last = str(e)[:80]
            time.sleep(2.0 * (attempt + 1))
    _err(n, last or "重试 3 次仍 0 条（抖音偶发限流）")
    return []


# ---------------------------------------------------------------- 快手
def kuaishou():
    """快手热榜。

    2026-10-17 实测：
      - 新版 https://www.kuaishou.com/new-reco 未登录只有 8 个导航链接，无热榜
      - 点「返回旧版」→ https://www.kuaishou.com/?isHome=1&source=NewReco
        **有公开的「快手热榜」**，容器 class=rank-container，条目含标题+热度
      - 直接访问旧版 URL 会 ERR_CONNECTION_CLOSED（要先从新版跳转带 cookie）
      - 新开 page 反复 goto 会被限流 → 复用 Chrome 9222 里已停靠的旧版标签页
    """
    n = "快手"
    js = r"""() => {
      const heads = [...document.querySelectorAll('*')].filter(
        e => e.children.length === 0 && (e.innerText || '').trim() === '快手热榜');
      if (!heads.length) return [];
      const h = heads[0];
      let box = h;
      for (let i = 0; i < 8 && box.parentElement; i++) {
        box = box.parentElement;
        const items = [...box.querySelectorAll('a')].filter(x => {
          const t = (x.innerText || '').trim();
          return t.length > 5 && t.length < 90;
        });
        if (items.length >= 5) {
          const seen = new Set(); const out = [];
          for (const x of items) {
            const raw = (x.innerText || '').trim();
            const lines = raw.split('\n').map(s => s.trim()).filter(Boolean);
            // 形如 ["高市早苗向靖国神社献祭品", "1152.3万热度"]，第一行是标题
            const title = lines[0] || '';
            if (!title || seen.has(title)) continue;
            seen.add(title);
            let hot = null;
            for (const ln of lines) { const m = ln.match(/([\d.]+)\s*万热度/); if (m) hot = Math.round(parseFloat(m[1]) * 10000); }
            out.push([title.slice(0, 90), String(x.href || '').slice(0, 160), hot]);
          }
          return out.slice(0, 50);
        }
      }
      return [];
    }"""
    data = cdp_reuse("kuaishou.com/?isHome", js, wait_ms=0)
    if data:
        out = []
        for i, (t, h, hot) in enumerate(data):
            out.append({"platform": n, "rank": i + 1, "title": t,
                        "url": h, "hot": hot, "tag": None})
        if out:
            _ok(n); return out
    _err(n, "CDP 9222 里没有快手旧版标签页。开法：Chrome --remote-debugging-port=9222 "
            "登录快手 → 打开 www.kuaishou.com/new-reco → 点「返回旧版」，然后重试")
    return []


# ---------------------------------------------------------------- 36氪 / 少数派 / IT之家
def ithome():
    n = "IT之家"
    try:
        import html as _h
        t = _get("https://www.ithome.com/rss/")
        out = []
        # 2026-10-17 修：旧正则要求 <link>，但 IT之家 RSS 的 item 里**没有 <link>**
        # （只有 title/description/pubDate/guid），所以永远匹配 0 条。
        # 改为按 item 块切，title 必取，link 从 guid/description 里找，找不到就留空。
        for m in re.finditer(r"<item>(.*?)</item>", t, re.S):
            blk = m.group(1)
            tm = re.search(r"<title>(.*?)</title>", blk, re.S)
            if not tm:
                continue
            title = _h.unescape(tm.group(1)).strip()
            if not title:
                continue
            url = ""
            gm = re.search(r"<guid[^>]*>(.*?)</guid>", blk, re.S)
            if gm and gm.group(1).startswith("http"):
                url = _h.unescape(gm.group(1)).strip()
            if not url:
                lm = re.search(r"https://www\.ithome\.com/0/\d+/\d+\.htm", blk)
                if lm:
                    url = lm.group(0)
            out.append({"platform": n, "rank": len(out) + 1, "title": title,
                        "url": url, "hot": None, "tag": None})
            if len(out) >= 30:
                break
        if out:
            _ok(n); return out
        _err(n, "RSS 0 条（len=%d）" % len(t))
    except Exception as e:
        _err(n, e)
    return []


def _render(url, wait_ms=4000, extract_js=None):
    """headless 渲染拿 SPA 数据（不需要登录的站点用）"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            pg = b.new_page(user_agent=UA)
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.wait_for_timeout(wait_ms)
            data = extract_js(pg) if extract_js else pg.content()
            b.close()
            return data
    except Exception as e:
        _err("render", e)
        return None


def kr36():
    n = "36氪"
    js = r"""() => {
      const out = [];
      document.querySelectorAll('a').forEach(a => {
        const t = (a.innerText || '').trim();
        const h = a.href || '';
        if (t.length > 12 && h.includes('/p/')) out.push([t, h]);
      });
      const seen = new Set(); const res = [];
      for (const y of out) { if (!seen.has(y[0])) { seen.add(y[0]); res.push(y); } }
      return res.slice(0, 30);
    }"""
    data = _render("https://www.36kr.com/hot-list/catalog", 5000, js)
    if not data:
        # 2026-10-17：headless 起不来时，复用 Chrome 9222 里已打开的 36氪 页
        data = cdp_reuse("36kr.com", js)
    if data:
        out = []
        for i, (t, h) in enumerate(data):
            out.append({"platform": n, "rank": i + 1, "title": t, "url": h, "hot": None, "tag": None})
        if out:
            _ok(n); return out
    _err(n, "SPA 渲染未取到条目（playwright 未装或页面结构变化）")
    return []


# ---------------------------------------------------------------- 澎湃 / 网易 / 腾讯新闻
def pengpai():
    n = "澎湃"
    # 旧接口 404、首页 403 → 走渲染；headless 不行就复用 CDP 9222
    js = r"""() => {
      const out = [];
      document.querySelectorAll('a').forEach(a => {
        const t = (a.innerText || '').trim();
        const h = a.href || '';
        if (t.length > 10 && (h.includes('newsDetail_forward') || h.includes('thepaper.cn'))) out.push([t, h]);
      });
      const seen = new Set(); const res = [];
      for (const y of out) { if (!seen.has(y[0])) { seen.add(y[0]); res.push(y); } }
      return res.slice(0, 25);
    }"""
    for u in ("https://www.thepaper.cn/list_115256", "https://www.thepaper.cn/channel_26916"):
        data = _render(u, 5000, js)
        if not data:
            data = cdp_reuse("thepaper.cn", js)
        if data:
            out = []
            for i, (t, h) in enumerate(data):
                out.append({"platform": n, "rank": i + 1, "title": t, "url": h, "hot": None, "tag": None})
            if out:
                _ok(n); return out
    _err(n, "整站 403，需登录态 Chrome（CDP 9222）或代理")
    return []


# ---------------------------------------------------------------- GitHub Trending
def github():
    n = "GitHub"
    try:
        t = _get("https://github.com/trending")
        out = []
        # 现在 <a> 里 data-hydro-click 属性很长，href 不在紧邻位置 → 改为就近向后搜 href
        for m in re.finditer(r'<h2 class="h3 lh-condensed">', t):
            seg = t[m.end():m.end() + 3000]
            href = re.search(r'href="/([\w.\-]+/[\w.\-]+)"', seg)
            if not href:
                continue
            rep = href.group(1).strip()
            desc = re.search(r'<p class="col-9 color-fg-muted my-1 pr-4">\s*(.*?)\s*</p>', seg, re.S)
            stars = re.search(r'([\d,]+)\s*stars', seg)
            lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', seg)
            out.append({"platform": n, "rank": len(out) + 1, "title": rep.replace("/", " / "),
                        "url": "https://github.com/" + rep,
                        "hot": int(stars.group(1).replace(",", "")) if stars else None,
                        "tag": lang.group(1) if lang else None})
            if len(out) >= 25:
                break
        if out:
            _ok(n); return out
        _err(n, "0 条")
    except Exception as e:
        _err(n, e)
    return []


# ---------------------------------------------------------------- Reddit（RSS 通道，JSON 接口 403）
def reddit():
    n = "Reddit"
    try:
        import html as _h
        t = _get("https://www.reddit.com/hot/.rss?limit=30")
        out = []
        for m in re.finditer(r"<entry>(.*?)</entry>", t, re.S):
            e = m.group(1)
            ti = re.search(r"<title>(.*?)</title>", e, re.S)
            lk = re.search(r'<link href="([^"]+)"', e)
            up = re.search(r'<updated>(.*?)</updated>', e)
            if not ti:
                continue
            out.append({"platform": n, "rank": len(out) + 1,
                        "title": _h.unescape(ti.group(1)).strip(),
                        "url": lk.group(1) if lk else "",
                        "hot": None, "tag": (up.group(1)[:10] if up else None)})
            if len(out) >= 30:
                break
        if out:
            _ok(n); return out
        _err(n, "RSS 0 条")
    except Exception as e:
        _err(n, e)
    return []
def hackernews():
    n = "HackerNews"
    try:
        from concurrent.futures import ThreadPoolExecutor
        ids = json.loads(_get("https://hacker-news.firebaseio.com/v0/topstories.json"))[:30]
        def one(nid):
            try:
                return json.loads(_get("https://hacker-news.firebaseio.com/v0/item/%d.json" % nid, timeout=15))
            except Exception:
                return None
        with ThreadPoolExecutor(10) as ex:
            items = [d for d in ex.map(one, ids) if d]
        out = []
        for i, d in enumerate(items):
            if not d.get("title"):
                continue
            out.append({"platform": n, "rank": len(out) + 1, "title": d["title"],
                        "url": d.get("url") or "https://news.ycombinator.com/item?id=%d" % d["id"],
                        "hot": d.get("score"), "tag": None})
        if out:
            _ok(n); return out
        _err(n, "0 条")
    except Exception as e:
        _err(n, e)
    return []


# ---------------------------------------------------------------- V2EX
def v2ex():
    n = "V2EX"
    try:
        d = json.loads(_get("https://www.v2ex.com/api/topics/hot.json"))
        out = []
        for i, v in enumerate(d):
            out.append({"platform": n, "rank": i + 1, "title": v.get("title"),
                        "url": v.get("url") or "https://www.v2ex.com/t/" + str(v.get("id")),
                        "hot": (v.get("member") or {}).get("id") and None,
                        "tag": v.get("node", {}).get("title") or None})
        if out:
            _ok(n); return out
    except Exception as e:
        _err(n, e)
    return []


ADAPTERS = [
    ("weibo", weibo), ("baidu", baidu), ("toutiao", toutiao), ("zhihu", zhihu),
    ("bilibili", bilibili), ("douyin", douyin), ("kuaishou", kuaishou),
    ("ithome", ithome), ("kr36", kr36), ("pengpai", pengpai),
    ("github", github), ("hackernews", hackernews), ("reddit", reddit), ("v2ex", v2ex),
]


def probe_all():
    from concurrent.futures import ThreadPoolExecutor
    res = {}
    def run(item):
        k, fn = item
        t0 = time.time()
        try:
            data = fn()
        except Exception as e:
            data = []
            _err(k, e)
        return k, {"count": len(data), "sec": round(time.time() - t0, 2),
                   "error": LAST_ERRORS.get(k), "sample": data[0] if data else None}
    with ThreadPoolExecutor(len(ADAPTERS)) as ex:
        for k, r in ex.map(run, ADAPTERS):
            res[k] = r
    return res


def fetch(platforms=None):
    out = []
    from concurrent.futures import ThreadPoolExecutor
    fns = ADAPTERS if not platforms else [a for a in ADAPTERS if a[0] in platforms]
    def run(item):
        try:
            return item[1]()
        except Exception as e:
            _err(item[0], e); return []
    with ThreadPoolExecutor(min(8, len(fns))) as ex:
        for data in ex.map(run, fns):
            out.extend(data)
    return out


if __name__ == "__main__":
    r = probe_all()
    print("\n%-12s %-6s %-7s %s" % ("平台", "条数", "耗时s", "状态"))
    print("-" * 80)
    for k, v in r.items():
        print("%-12s %-6d %-7.2f %s" % (k, v["count"], v["sec"],
                                        "OK" if v["count"] else ("FAIL: " + (v["error"] or "0 条")[:60])))
    total = sum(v["count"] for v in r.values())
    ok = sum(1 for v in r.values() if v["count"])
    print("\n[✓] 可用源 %d/%d，真实抓到 %d 条" % (ok, len(r), total))
    for k, v in r.items():
        if v["sample"]:
            print("   样例[%s] %s" % (k, v["sample"]["title"][:60]))
