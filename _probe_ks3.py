#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手：点「返回旧版」找公开热榜；再试移动端"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    pg = ctx.new_page()
    pg.goto("https://www.kuaishou.com/new-reco", timeout=45000,
            wait_until="domcontentloaded")
    pg.wait_for_timeout(4000)
    try:
        pg.get_by_text("返回旧版", exact=True).first.click(timeout=5000)
        pg.wait_for_timeout(5000)
        print("旧版 URL:", pg.url)
        txt = pg.evaluate("() => document.body.innerText.slice(0, 900)")
        print("--- 旧版 body ---")
        print(txt)
        links = pg.evaluate(
            "() => [...document.querySelectorAll('a')].map(a=>"
            "(a.innerText||'').trim()+' | '+String(a.href||'').slice(0,70))"
            ".filter(x=>x.length>4).slice(0,30)")
        print("--- 旧版 links ---")
        for x in links:
            print("  ", x)
    except Exception as e:
        print("返回旧版失败:", str(e)[:80])
    pg.close()

    pg2 = ctx.new_page()
    for u in ("https://m.kuaishou.com/", "https://www.kuaishou.com/?isHome=1"):
        try:
            pg2.goto(u, timeout=35000, wait_until="domcontentloaded")
            pg2.wait_for_timeout(3500)
            print("== %s -> %s" % (u, pg2.url))
            t = pg2.evaluate("() => document.body.innerText.slice(0,400)")
            print(t.replace("\n", " / ")[:400])
        except Exception as e:
            print("== %s ERR %s" % (u, str(e)[:60]))
    pg2.close()
