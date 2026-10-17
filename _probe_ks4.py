#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手热榜 DOM 结构定位"""
from playwright.sync_api import sync_playwright

JS = r"""() => {
  // 找含「热榜」文字的标题元素，向上找容器，再列出该容器内的条目
  const heads = [...document.querySelectorAll('*')].filter(
    e => e.children.length === 0 && (e.innerText || '').trim() === '快手热榜');
  const out = [];
  for (const h of heads) {
    let box = h;
    for (let i = 0; i < 6 && box.parentElement; i++) {
      box = box.parentElement;
      const items = box.querySelectorAll('a, div, li');
      const withText = [...items].filter(x => {
        const t = (x.innerText || '').trim();
        return t.length > 6 && t.length < 90 && x.children.length <= 2;
      });
      if (withText.length >= 5) {
        out.push({
          depth: i,
          boxClass: String(box.className || '').slice(0, 60),
          boxTag: box.tagName,
          n: withText.length,
          sample: withText.slice(0, 6).map(x => [
            (x.innerText || '').trim().slice(0, 50),
            (x.querySelector('a') ? x.querySelector('a').href : (x.href || '')).slice(0, 80)
          ])
        });
        break;
      }
    }
  }
  return out;
}"""

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    pg = ctx.new_page()
    print("goto new-reco ...", flush=True)
    pg.goto("https://www.kuaishou.com/new-reco", timeout=30000,
            wait_until="domcontentloaded")
    pg.wait_for_timeout(3000)
    print("clicking 返回旧版 ...", flush=True)
    try:
        pg.get_by_text("返回旧版", exact=True).first.click(timeout=6000, no_wait_after=True)
        pg.wait_for_timeout(6000)
    except Exception as e:
        print("返回旧版失败:", str(e)[:60], flush=True)
    print("URL:", pg.url, flush=True)
    r = pg.evaluate(JS)
    for x in r:
        print("depth=%s box=%s.%s n=%d" % (x["depth"], x["boxTag"], x["boxClass"], x["n"]))
        for s in x["sample"]:
            print("   ", s)
        print()
    pg.close()
