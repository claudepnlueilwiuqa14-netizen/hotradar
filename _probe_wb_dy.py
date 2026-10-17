#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微博热榜 DOM 结构 + 抖音精选 tab=hot 结构"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]

    print("=== 微博 ===")
    for x in ctx.pages:
        if "s.weibo.cn/top/summary" in (x.url or ""):
            print("URL:", x.url)
            r = x.evaluate(r"""() => {
              const out = {links: [], classes: []};
              document.querySelectorAll('a').forEach(a => {
                const t = (a.innerText || '').trim();
                if (t.length > 3 && t.length < 90) {
                  out.links.push([t.slice(0, 70), String(a.href || '').slice(0, 90)]);
                }
              });
              out.links = out.links.slice(0, 15);
              document.querySelectorAll('div,ul,li,table').forEach(e => {
                const c = String(e.className || '');
                if (c && e.children.length >= 3) {
                  const t = (e.innerText || '').trim();
                  if (t.length > 30 && t.length < 400) {
                    out.classes.push(e.tagName + '.' + c.slice(0, 40) + ' n=' + e.children.length);
                  }
                }
              });
              out.classes = [...new Set(out.classes)].slice(0, 12);
              return out;
            }""")
            print("links:")
            for y in r["links"][:12]:
                print("   ", y)
            print("containers:")
            for y in r["classes"]:
                print("   ", y)
            break

    print("\n=== 抖音精选 tab=hot ===")
    target = None
    for x in ctx.pages:
        if "douyin.com/jingxuan" in (x.url or "") and "tab=hot" in (x.url or ""):
            target = x
            break
    if target is None:
        for x in ctx.pages:
            if "douyin.com/jingxuan" in (x.url or ""):
                target = x
                break
    if target:
        print("URL:", target.url)
        r = target.evaluate(r"""() => {
          const out = [];
          document.querySelectorAll('a,div,span').forEach(e => {
            const t = (e.innerText || '').trim();
            const c = String(e.className || '');
            if (t.length > 6 && t.length < 80 && e.children.length <= 1) {
              out.push([t.slice(0, 70), c.slice(0, 40), String(e.href || '').slice(0, 60)]);
            }
          });
          const seen = new Set(); const res = [];
          for (const y of out) { if (!seen.has(y[0])) { seen.add(y[0]); res.push(y); } }
          return res.slice(0, 40);
        }""")
        print("items:", len(r))
        for y in r[:25]:
            print("   ", y)
    else:
        print("没有抖音精选标签页")
