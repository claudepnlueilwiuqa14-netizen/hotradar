#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CDP 工具增强版：复用已打开标签页，避免新开页触发限流。

2026-10-17 实测结论：
  - 新开 page 反复 goto kuaishou.com 会 ERR_CONNECTION_CLOSED（被限流）
  - Chrome 9222 里已有 31 个标签页，其中 s.weibo.cn / kuaishou 旧版 /
    douyin jingxuan 都是登录态 → **复用它们，不开新页**
"""
import json
import time
import urllib.request

CDP_URL = "http://127.0.0.1:9222"


def _cdp_list():
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        r = op.open(urllib.request.Request(CDP_URL + "/json/list",
                                           headers={"User-Agent": "Mozilla/5.0"}),
                    timeout=8)
        return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return []


def cdp_pages():
    return [t for t in _cdp_list() if t.get("type") == "page"]


def cdp_reuse(url_part, js, wait_ms=0, reload_first=False):
    """在已打开的标签页里找 url_part，直接 evaluate。找不到返回 None。

    reload_first=True 时先 reload（有些标签页停靠在后台没渲染完）。
    """
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP_URL)
            ctx = b.contexts[0] if b.contexts else None
            if ctx is None:
                return None
            pg = None
            for x in ctx.pages:
                if url_part in (x.url or ""):
                    pg = x
                    break
            if pg is None:
                return None
            if reload_first:
                try:
                    pg.reload(timeout=30000, wait_until="domcontentloaded")
                except Exception:
                    pass
            if wait_ms:
                pg.wait_for_timeout(wait_ms)
            return pg.evaluate(js)
    except Exception as e:
        try:
            import sources as _S
            _S._err("cdp-reuse", e)
        except Exception:
            pass
        return None


def cdp_open(url, js, wait_ms=4000):
    """没有现成标签页时才新开一个（新开有被限流风险，尽量少用）。"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP_URL)
            ctx = b.contexts[0] if b.contexts else b.new_context()
            pg = ctx.new_page()
            pg.goto(url, timeout=40000, wait_until="domcontentloaded")
            pg.wait_for_timeout(wait_ms)
            r = pg.evaluate(js)
            try:
                pg.close()
            except Exception:
                pass
            return r
    except Exception as e:
        try:
            import sources as _S
            _S._err("cdp-open", e)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------- 通用 JS
JS_LINKS = r"""() => {
  const out = [];
  document.querySelectorAll('a').forEach(a => {
    const t = (a.innerText || '').trim();
    if (t.length > 5 && t.length < 90) out.push([t.slice(0, 90), String(a.href || '').slice(0, 140)]);
  });
  const seen = new Set(); const res = [];
  for (const y of out) { if (!seen.has(y[0])) { seen.add(y[0]); res.push(y); } }
  return res;
}"""
