#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hotradar.analyze —— 跨平台热点搜索与分析
输入一个关键词 → 跨所有平台搜 → 输出结构化分析 + Markdown 报告。

分析维度：
  1. 命中分布（哪些平台在谈、各多少条、排在最前面的是谁）
  2. 热度分级（按 hot 值分档）
  3. 标题共现词（自动切词统计，找出真正的高频概念）
  4. 跨平台同时上榜 = 强信号
  5. 建议（要不要追、追哪个平台）
"""
import re, json, time
from collections import Counter, defaultdict

STOP = set("""的 了 是 在 和 与 及 对 为 被 把 有 没 不 无 我 你 他 她 它 们 个 之 其 也 都 就 还 但 或 如果 因为 所以 这个 那个 什么 怎么 如何 一个 一些 现在 已经 可以 不会 不能 应该 可能 或者 以及 之后 之前 时候 问题 事情 东西 大家 网友 表示 认为 说 称 报道 发布 推出 宣布 曝光 回应 视频 视频中 网传 最新 回应称 引起 网友称 the a an of to in on for and or is are was were with by at from as it this that""".split())

CJK = re.compile(r"[\u4e00-\u9fff]{2,}")
EN = re.compile(r"[A-Za-z][A-Za-z0-9\-\+\.#]{2,}")


def tokenize(text):
    out = []
    for m in CJK.finditer(text or ""):
        w = m.group(0)
        # 中文无空格切分：取 2-gram 与 3-gram，再叠加去停用
        if len(w) <= 4:
            out.append(w)
        else:
            out.extend(w[i:i + 2] for i in range(len(w) - 1))
            out.extend(w[i:i + 3] for i in range(len(w) - 2))
    for m in EN.finditer(text or ""):
        out.append(m.group(0).lower())
    return [w for w in out if w not in STOP and len(w) >= 2]


def search(data, kw):
    kw_l = kw.lower()
    return [d for d in data if kw_l in (d.get("title") or "").lower()]


def analyze(data, kw):
    hits = search(data, kw)
    byp = defaultdict(list)
    for h in hits:
        byp[h["platform"]].append(h)
    # 共现词
    c = Counter()
    for h in hits:
        c.update(tokenize(h["title"]))
    co = [w for w, n in c.most_common(40) if n >= 2][:20]
    # 热度分档
    def tier(h):
        v = h.get("hot") or 0
        if v >= 1000000: return "爆(100w+)"
        if v >= 100000: return "热(10w+)"
        if v >= 10000: return "温(1w+)"
        if v: return "微"
        return "未知"
    tiers = Counter(tier(h) for h in hits)
    # 跨平台强信号
    strong = [p for p, v in byp.items() if len(v) >= 2]
    return {
        "keyword": kw, "total": len(hits), "platform_count": len(byp),
        "by_platform": {p: len(v) for p, v in sorted(byp.items(), key=lambda x: -len(x[1]))},
        "top_per_platform": {p: [{"rank": x["rank"], "title": x["title"], "hot": x.get("hot")} for x in v[:5]]
                             for p, v in byp.items()},
        "cooccurring": co, "heat_tiers": dict(tiers),
        "cross_platform_strong": strong,
        "hits": hits,
    }


def report(data, kw):
    a = analyze(data, kw)
    L = []
    L.append("# 热点分析报告：%s" % kw)
    L.append("\n> 生成时间 %s · 命中 **%d** 条 · 覆盖 **%d** 个平台\n" % (time.strftime("%F %T"), a["total"], a["platform_count"]))
    L.append("## 1. 平台分布\n")
    L.append("| 平台 | 命中数 |")
    L.append("|---|---|")
    for p, n in a["by_platform"].items():
        L.append("| %s | %d |" % (p, n))
    L.append("\n## 2. 各平台前排\n")
    for p, items in a["top_per_platform"].items():
        L.append("**%s**" % p)
        for it in items:
            L.append("  - #%s %s%s" % (it["rank"], it["title"],
                                        ("（热度 %s）" % it["hot"]) if it.get("hot") else ""))
        L.append("")
    L.append("## 3. 高频共现词\n")
    L.append("、".join("`%s`" % w for w in a["cooccurring"]) or "（样本不足）")
    L.append("\n## 4. 热度分档\n")
    for k, v in a["heat_tiers"].items():
        L.append("- %s：%d 条" % (k, v))
    L.append("\n## 5. 结论与建议\n")
    if a["platform_count"] >= 3:
        L.append("- **强信号**：%s 同时在 %d 个平台在榜，属于跨平台级热点，值得立刻跟进。"
                 % (kw, a["platform_count"]))
    elif a["platform_count"] == 1:
        L.append("- 只在 %s 单平台出现，属于垂直/局部热度，按该平台受众定向追。"
                 % list(a["by_platform"])[0])
    else:
        L.append("- 覆盖 %d 个平台，中等热度。" % a["platform_count"])
    if a["cooccurring"]:
        L.append("- 核心概念词：%s —— 做内容时围绕这些词展开更容易被推荐。" % "、".join(a["cooccurring"][:8]))
    return "\n".join(L)


if __name__ == "__main__":
    import sources as S
    data = S.fetch()
    kw = input("关键词：").strip() or "AI"
    print(report(data, kw))
