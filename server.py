#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hotradar.server —— 全平台热点雷达 HTTP 服务（纯标准库，无第三方依赖）

接口：
  GET /api/platforms            各源实时状态（条数/耗时/错误）
  GET /api/hot[?platform=xxx]   拉一次全站热榜（platform 可逗号分隔）
  GET /api/search?q=关键词      跨所有平台搜，返回命中项
  GET /api/diff?hours=6         与 N 小时前快照对比：新增/升榜/掉榜/爆榜
  GET /api/snapshot             保存一次快照并返回
  GET /api/analyze?q=关键词     生成 Markdown 分析报告
  GET /health

用法：python server.py [--port 8790] [--once]
"""
import argparse, json, os, sqlite3, sys, time, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources as S

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "hotradar.db")
CACHE_SEC = 120
_lock = threading.Lock()
_mem = {"ts": 0, "data": []}


def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS snap (ts INTEGER, platform TEXT, rank INTEGER, title TEXT, url TEXT, hot INTEGER, tag TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS errlog (ts INTEGER, platform TEXT, err TEXT)")
    c.commit()
    return c


def pull(force=False, platforms=None):
    """拉一次全站热榜，带 120s 内存缓存。
    注意：按平台子集拉取时**不写**全站缓存，避免把部分结果污染成全站快照。"""
    with _lock:
        if platforms and not force:
            return S.fetch(platforms)
        if not force and _mem["data"] and time.time() - _mem["ts"] < CACHE_SEC:
            return _mem["data"]
        data = S.fetch()
        _mem["data"], _mem["ts"] = data, time.time()
        return data


def save_snapshot(data=None):
    data = data or pull()
    c = db()
    c.executemany("INSERT INTO snap VALUES (?,?,?,?,?,?,?)",
                  [(int(time.time()), d["platform"], d["rank"], d["title"], d.get("url") or "",
                    d.get("hot") or 0, d.get("tag") or "") for d in data])
    for p, e in list(S.LAST_ERRORS.items()):
        c.execute("INSERT INTO errlog VALUES (?,?,?)", (int(time.time()), p, e))
    c.commit(); c.close()
    return len(data)


def diff(hours=6):
    """与 hours 前的快照对比。"""
    now = int(time.time()); before = now - int(hours * 3600)
    c = db()
    cur = c.execute("SELECT platform,title,rank,hot FROM snap WHERE ts>=? ORDER BY ts DESC", (now - CACHE_SEC - 300,)).fetchall()
    old = c.execute("SELECT platform,title,rank,hot FROM snap WHERE ts<=? ORDER BY ts DESC", (before,)).fetchall()
    c.close()
    if not old:
        return {"error": "没有 %d 小时前的快照，先跑一次 /api/snapshot 等一段时间再对比" % hours}
    curm = {}
    for p, t, r, h in cur:
        curm.setdefault((p, t), (r, h))
    oldm = {}
    for p, t, r, h in old:
        oldm.setdefault((p, t), (r, h))
    new = [{"platform": p, "title": t, "rank": r} for (p, t), (r, h) in curm.items() if (p, t) not in oldm]
    gone = [{"platform": p, "title": t, "rank": r} for (p, t), (r, h) in oldm.items() if (p, t) not in curm]
    up = []
    for k, (r, h) in curm.items():
        if k in oldm and oldm[k][0] and r and r < oldm[k][0]:
            up.append({"platform": k[0], "title": k[1], "from": oldm[k][0], "to": r})
    up.sort(key=lambda x: x["from"] - x["to"], reverse=True)
    boom = [x for x in up if x["from"] - x["to"] >= 10]
    return {"new": new[:60], "gone": gone[:60], "up": up[:60], "boom": boom[:30],
            "counts": {"new": len(new), "gone": len(gone), "up": len(up), "boom": len(boom)}}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _j(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        one = lambda k, d=None: (q.get(k) or [d])[0]
        try:
            if p == "/health":
                return self._j(200, {"ok": True, "ts": time.strftime("%F %T")})
            if p == "/api/platforms":
                r = S.probe_all()
                return self._j(200, {"ts": time.strftime("%F %T"), "platforms": r})
            if p == "/api/hot":
                pl = one("platform")
                data = pull(platforms=pl.split(",") if pl else None)
                if one("force") in ("1", "true"):
                    data = pull(force=True, platforms=pl.split(",") if pl else None)
                byp = {}
                for d in data:
                    byp.setdefault(d["platform"], []).append(d)
                return self._j(200, {"ts": time.strftime("%F %T"), "total": len(data),
                                     "platforms": sorted(byp.keys()),
                                     "data": data, "by_platform": byp,
                                     "errors": S.LAST_ERRORS})
            if p == "/api/search":
                kw = (one("q") or "").strip()
                if not kw:
                    return self._j(400, {"error": "缺 q 参数"})
                data = pull()
                hits = [d for d in data if kw.lower() in d["title"].lower()]
                byp = {}
                for d in hits:
                    byp.setdefault(d["platform"], []).append(d)
                return self._j(200, {"q": kw, "total": len(hits), "by_platform": byp, "hits": hits})
            if p == "/api/snapshot":
                n = save_snapshot()
                return self._j(200, {"saved": n, "ts": time.strftime("%F %T")})
            if p == "/api/diff":
                return self._j(200, diff(float(one("hours", "6"))))
            if p == "/api/analyze":
                import analyze
                kw = (one("q") or "").strip()
                if not kw:
                    return self._j(400, {"error": "缺 q 参数"})
                md = analyze.report(pull(), kw)
                return self._j(200, {"q": kw, "markdown": md})
            return self._j(404, {"error": "not found", "path": p})
        except Exception as e:
            return self._j(500, {"error": str(e)[:300]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--once", action="store_true", help="只拉一次并保存快照，然后退出")
    a = ap.parse_args()
    if a.once:
        d = pull(force=True)
        print("[✓] 拉到 %d 条，保存快照 %d 条" % (len(d), save_snapshot(d)))
        return
    print("[i] hotradar http://127.0.0.1:%d" % a.port, flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
