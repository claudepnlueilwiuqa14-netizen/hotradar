#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手热榜入口探测：找 new-reco 页面里真实的热榜结构"""
import sys
from playwright.sync_api import sync_playwright

JS = r"""() => {
  const out = {links: [], hottext: []};
  document.querySelectorAll('a').forEach(a => {
    const t = (a.innerText || '').trim();
    if (t && t.length < 40) out.links.push(t + ' | ' + String(a.href || '').slice(0, 70));
  });
  out.links = out.links.slice(0, 40);
  const re = /hot|rank|top|榜/i;
  document.querySelectorAll('*').forEach(e => {
    const c = String(e.className || '') + ' ' + String(e.id || '');
    if (re.test(c) && e.children.length < 30) {
      const t = (e.innerText || '').trim();
      if (t && t.length > 10 && t.length < 400) {
        out.hottext.push(c.slice(0, 40) + ' :: ' + t.slice(0, 200).replace(/\n/g, ' / '));
      }
    }
  });
  out.hottext = out.hottext.slice(0, 15);
  return out;
}"""

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    pg = ctx.new_page()
    pg.goto("https://www.kuaishou.com/new-reco", timeout=45000,
            wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    r = pg.evaluate(JS)
    print("URL:", pg.url)
    print("--- LINKS (%d) ---" % len(r["links"]))
    for x in r["links"][:30]:
        print("  ", x)
    print("--- HOT-ISH (%d) ---" % len(r["hottext"]))
    for x in r["hottext"][:12]:
        print("  ", x)
    pg.close()
