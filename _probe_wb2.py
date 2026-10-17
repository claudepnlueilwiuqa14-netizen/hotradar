#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微博 CDP 标签页真实内容诊断"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    for x in ctx.pages:
        if "s.weibo.cn/top/summary" in (x.url or ""):
            print("URL:", x.url)
            try:
                x.reload(timeout=30000, wait_until="domcontentloaded")
                x.wait_for_timeout(4000)
            except Exception as e:
                print("reload err:", str(e)[:80])
            print("after reload URL:", x.url)
            print("title:", x.title())
            t = x.evaluate("() => document.body ? document.body.innerText.slice(0, 900) : 'NO BODY'")
            print("--- text ---")
            print(t)
            links = x.evaluate(
                "() => [...document.querySelectorAll('a')].map(a=>"
                "(a.innerText||'').trim().slice(0,50)+' || '+String(a.href||'').slice(0,70))"
                ".filter(s=>s.length>6).slice(0,25)")
            print("--- links ---")
            for y in links:
                print("  ", y)
            break
