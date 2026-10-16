# hotradar · 全平台热点雷达

跨 14 个平台实时抓热榜 + 全站关键词搜索 + 结构化分析报告。纯 Python 标准库，无第三方依赖。

> 2026-10-16 本机实测：**10/14 源可用，真实抓到 389 条**。

## 快速开始

```bash
# 1) 先看哪些源能通（并发探测，真实回显）
python sources.py

# 2) 起服务（默认 8804）
python server.py --port 8804

# 3) 用
curl "http://127.0.0.1:8804/api/hot"                      # 全站热榜
curl "http://127.0.0.1:8804/api/search?q=AI"              # 跨平台搜关键词
curl "http://127.0.0.1:8804/api/analyze?q=特斯拉"          # 生成 Markdown 分析报告
curl "http://127.0.0.1:8804/api/snapshot"                 # 存快照
curl "http://127.0.0.1:8804/api/diff?hours=6"             # 6 小时对比：新增/升榜/掉榜/爆榜
```

## 接口

| 接口 | 说明 |
|---|---|
| `GET /health` | 存活检查 |
| `GET /api/platforms` | 各源实时状态（条数/耗时/错误原因） |
| `GET /api/hot?platform=baidu,douyin&force=1` | 全站或指定平台热榜 |
| `GET /api/search?q=关键词` | 跨所有平台搜，按平台分组返回 |
| `GET /api/analyze?q=关键词` | Markdown 分析报告 |
| `GET /api/snapshot` / `GET /api/diff?hours=6` | 快照与增量对比 |

## 平台覆盖（实测）

| 平台 | 状态 | 条数 | 说明 |
|---|---|---|---|
| 百度热搜 | ✅ | 50 | `top.baidu.com/api/board`（返回是**两层嵌套**，要剥两层） |
| 今日头条 | ✅ | 50 | `toutiao.com/hot-event/hot-board` |
| 知乎热榜 | ✅ | 30 | 主接口失效时回退 `search/top_search` |
| B 站热门 | ✅ | 100 | `-352` 反爬会偶发，已加 3 次退避重试 |
| 抖音热点 | ✅ | 49 | 偶发限流，已加 3 次退避重试 |
| IT 之家 | ✅ | 30 | RSS |
| GitHub Trending | ✅ | 12 | `<a>` 里 `data-hydro-click` 很长，`href` 不在紧邻位置，要就近向后搜 |
| Hacker News | ✅ | 30 | 30 个 item **并发**取（串行要 66s，并发 7s） |
| Reddit | ✅ | 30 | JSON 接口 403，改走 `.rss` |
| V2EX | ✅ | 8 | 官方 API |
| 微博热搜 | ⚠️ | - | 桌面 403 / 移动端访客系统 → 需登录态 Chrome（CDP 9222），代码已接好 `cdp_fetch()` |
| 快手 | ⚠️ | - | 需登录态，同上 |
| 36 氪 | ⚠️ | - | SPA，headless 渲染未取到条目 |
| 澎湃 | ⚠️ | - | 整站 403，需登录态或代理 |

## 接登录态 Chrome（微博/快手）

WorkBuddy 沙箱会回收 GUI 进程，但**用户自己启动的 Chrome 不受影响**：

```bash
# 手动启动（只需一次）
chrome.exe --remote-debugging-port=9222
# 用它登录微博 / 快手
```

之后 `weibo()` 会自动走 CDP 兜底通道（`sources.py: cdp_fetch()`）。

## 分析维度

`analyze.py` 对任意关键词输出：

1. **平台分布** —— 哪些平台在谈、各多少条
2. **各平台前排** —— 每个平台排名最前的命中项 + 热度值
3. **高频共现词** —— 中文 2/3-gram + 英文词，去停用词后统计，找出真正的高频概念
4. **热度分档** —— 爆(100w+) / 热(10w+) / 温(1w+) / 微 / 未知
5. **结论建议** —— ≥3 平台同时在榜判为跨平台强信号；单平台判为垂直热度

## 实测样例（2026-10-16 真实数据）

```
=== AI  命中 26 覆盖平台 9
  分布: {'Reddit': 7, 'IT之家': 5, '知乎': 3, 'B站': 3, 'HackerNews': 3, '百度': 2, '抖音': 1, 'GitHub': 1, 'V2EX': 1}

=== 特斯拉  命中 5 覆盖平台 4
  [抖音] #1 特斯拉发布第二代Roadster跑车（热度 11461406）
  [知乎] #22 特斯拉新款 Roadster 正式亮相，能实现离地升空、空中翻滚，如何评价？
  [IT之家] #4 特斯拉能飞：第二代 Roadster 预订意向金 33.2 万元起，马斯克宣布 2028 年量产
  → 强信号：跨平台级热点
```

## 文件

```
sources.py   14 个平台适配器 + CDP 兜底 + 并发探测
server.py    HTTP 服务（纯标准库）
analyze.py   搜索与分析、Markdown 报告
hotradar.db  快照存储（自动建表）
```

## 已知边界

- 微博/快手/36氪/澎湃 4 个源需登录态或代理，代码已就位，**不伪造数据**，失败时 `/api/hot` 的 `errors` 字段会给出真实原因
- `python sources.py` 的探测是全并发，约 20–40 秒
