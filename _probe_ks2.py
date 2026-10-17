#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手：找顶部 tab，尝试点进热榜"""
from playwright.sync_api import sync_playwright

JS_TABS = r"""() => {
  const out = [];
  document.querySelectorAll('div,span,li,a').forEach(e => {
    const t = (e.innerText || '').trim();
    if (t && t.length <= 6 && e.children.length === 0) out.push(t);
  });
  return [...new Set(out)].slice(0, 60);
}"""

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    pg = ctx.new_page()
    pg.goto("https://www.kuaishou.com/new-reco", timeout=45000,
            wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    print("TABS:", pg.evaluate(JS_TABS))
    # 尝试点「热榜」
    for name in ("热榜", "热点", "热搜"):
        try:
            el = pg.get_by_text(name, exact=True).first
            if el.count() if hasattr(el, "count") else True:
                el.click(timeout=4000)
                pg.wait_for_timeout(4000)
                print("clicked %s -> %s" % (name, pg.url))
                break
        except Exception as e:
            print("click %s failed: %s" % (name, str(e)[:60]))
    print("URL now:", pg.url)
    txt = pg.evaluate("() => document.body.innerText.slice(0, 1200)")
    print("--- body text ---")
    print(txt)
    pg.close()
