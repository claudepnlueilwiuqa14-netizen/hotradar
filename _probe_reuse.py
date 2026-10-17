#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复用 Chrome 9222 里已打开的标签页抓热榜（不开新页，避开限流）"""
import json
import urllib.request
from playwright.sync_api import sync_playwright

UA = {"User-Agent": "Mozilla/5.0"}


def cdp_tabs():
    r = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(r.open(urllib.request.Request(
        "http://127.0.0.1:9222/json/list", headers=UA), timeout=8).read())


WEIBO_JS = r"""() => {
  const out = [];
  document.querySelectorAll('a').forEach(a => {
    const t = (a.innerText || '').trim();
    const h = a.href || '';
    if (t.length > 3 && t.length < 90 && (h.includes('/weibo?q=') || h.includes('s.weibo.cn/weibo'))) {
      out.push([t.slice(0, 90), h.slice(0, 120)]);
    }
  });
  const seen = new Set(); const res = [];
  for (const [t, h] of out) { if (!seen.has(t)) { seen.add(t); res.push([t, h]); } }
  return res.slice(0, 50);
}"""

KS_JS = r"""() => {
  const heads = [...document.querySelectorAll('*')].filter(
    e => e.children.length === 0 && (e.innerText || '').trim() === '快手热榜');
  if (!heads.length) return {err: 'no 快手热榜 heading', body: document.body.innerText.slice(0, 200)};
  const h = heads[0];
  let box = h;
  for (let i = 0; i < 8 && box.parentElement; i++) {
    box = box.parentElement;
    const items = [...box.querySelectorAll('a,div,li,span')].filter(x => {
      const t = (x.innerText || '').trim();
      return t.length > 5 && t.length < 90 && x.children.length <= 2;
    });
    if (items.length >= 5) {
      return {depth: i, box: String(box.className || '').slice(0, 60),
              items: items.slice(0, 20).map(x => [
                (x.innerText || '').trim().slice(0, 80),
                (x.querySelector('a') ? x.querySelector('a').href : (x.href || '')).slice(0, 110)])};
    }
  }
  return {err: 'container not found'};
}"""

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    tabs = {t["url"]: t for t in cdp_tabs() if t.get("type") == "page"}

    print("=== 微博 ===")
    for url, t in tabs.items():
        if "s.weibo.cn/top/summary" in url:
            pg = None
            for x in ctx.pages:
                if "s.weibo.cn/top/summary" in (x.url or ""):
                    pg = x
                    break
            if pg:
                r = pg.evaluate(WEIBO_JS)
                print("reuse %s -> %d items" % (pg.url[:50], len(r)))
                for x in r[:8]:
                    print("   ", x)
            break

    print("\n=== 快手 ===")
    for url, t in tabs.items():
        if "kuaishou.com/?isHome" in url:
            pg = None
            for x in ctx.pages:
                if "kuaishou.com/?isHome" in (x.url or ""):
                    pg = x
                    break
            if pg:
                r = pg.evaluate(KS_JS)
                print("reuse %s" % pg.url[:50])
                print(json.dumps(r, ensure_ascii=False)[:1600])
            break

    print("\n=== 抖音精选 hot ===")
    for url, t in tabs.items():
        if "douyin.com/jingxuan" in url:
            pg = None
            for x in ctx.pages:
                if "douyin.com/jingxuan" in (x.url or ""):
                    pg = x
                    break
            if pg:
                r = pg.evaluate(r"""() => {
                  const out = [];
                  document.querySelectorAll('a').forEach(a => {
                    const t = (a.innerText || '').trim();
                    if (t.length > 5 && t.length < 90) out.push([t.slice(0,80), String(a.href||'').slice(0,100)]);
                  });
                  const seen = new Set(); const res = [];
                  for (const [t,h] of out) { if (!seen.has(t)) { seen.add(t); res.push([t,h]); } }
                  return res.slice(0, 25);
                }""")
                print("reuse %s -> %d" % (pg.url[:50], len(r)))
                for x in r[:10]:
                    print("   ", x)
            break
