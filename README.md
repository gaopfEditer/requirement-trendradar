# 海外需求雷达 v1.1

把 **Google Trends 热词** 与 **Product Hunt / CSV 排行变更** 交叉成可筛选的「机会卡」，通过静态站展示。内部决策工具：不自动投标、不绕登录爬付费站。

## 预览 URL

启用 GitHub Pages（Settings → Pages → Source: **GitHub Actions**）后，站点地址为：

**https://gaopfEditer.github.io/requirement-trendradar/**

（合并本仓库并跑通一次 `Deploy GitHub Pages` 或 `Daily Demand Radar` workflow 后即可访问。）

### GitHub Pages 部署注意

- 使用 workflow：**Actions → Deploy GitHub Pages → Run workflow**（`workflow_dispatch`），或向 `main` push 触发。
- **不要**对已经执行过 `upload-pages-artifact` 的 run 使用 **Re-run failed jobs**。该操作会在同一 run 内再上传一个同名 `github-pages` artifact，导致 `deploy-pages` 报错：`Multiple artifacts named "github-pages" were unexpectedly found`。
- 若部署失败，请 **新开一次完整 run**（重新 Run workflow 或空提交 push），保证单次 run 只有一个 `github-pages` artifact。
- 工作流已设置 `concurrency: pages` + `cancel-in-progress: true`，避免并发部署互相干扰。

## 流水线五步（A–E + D 发布）

| 步骤 | 命令 | 说明 |
|------|------|------|
| A | `python -m scripts.ingest_trends` | 读种子词 → 拉 Trends → `raw/trends_YYYYMMDD.json` + `data/trends_daily.json`（`trends_source`: live/demo） |
| B | `python -m scripts.ingest_rankings` | Product Hunt 公开 Atom Feed + `uploads/rankings*.csv` → `rankings_daily` / `rankings_delta` |
| C | `python -m scripts.build_opportunity_cards` | 交叉合成机会卡，已设 `verdict_manual: true` 的不覆盖 verdict |
| E | `python -m scripts.build_weekly_movers` | 周增长榜 → `data/weekly_movers.json`（周一或足够历史时计算，否则 fixture） |
| D | `python -m scripts.publish_site` | 写 `meta.json` + 复制 JSON 到 `public/data/` |

一键跑全流程（在项目根目录）：

```bash
pip install -r requirements.txt
export PYTHONPATH=.
python -m scripts.run_pipeline --demo    # 离线演示（fixtures）
python -m scripts.run_pipeline           # 真实公开源（受网络/IP 限制）
python -m scripts.run_pipeline --csv-only  # 排行仅 CSV，跳过 PH
```

失败会写入 `data/runs.json`，对应网站 **Runs** 页，不会静默吞错。

### GitHub Actions 定时

- Workflow：`.github/workflows/daily-radar.yml`（显示名 **Demand Radar Pipeline**）
- **每 4 小时**全流水线：cron `0 */4 * * *`（UTC，约香港 08/12/16/20/00/04 点）
- **接单帖**单独 workflow：`.github/workflows/job-leads.yml`，同样 **每 4 小时**（`0 */4 * * *`），抓取后 **默认合并** `recommend=true` 到 `opportunities.json`，与首页机会卡保持同步
- 额外 **周一 09:00 香港** 触发：`0 1 * * 1` UTC（与 4h 重叠时 concurrency 只跑一轮）
- 手动触发：Actions → **Demand Radar Pipeline** → **Run workflow**（`demo` / `csv_only` 仍可用）
- 并发：`demand-radar-pipeline` + `cancel-in-progress: true`（与 Pages 的 `pages` concurrency 分开）
- **勿**对已 upload 的 run 做 **Re-run failed jobs**；失败请 workflow_dispatch 或新 push（见上文 Pages 说明）

### 全站更新时间（meta.json）

`publish_site` 写入 `data/meta.json` / `public/data/meta.json`：

| 字段 | 说明 |
|------|------|
| `updated_at` | 最近一次成功写出机会卡的时间，ISO `+08:00` |
| `schedule` | `every_4h` |
| `last_run_ok` / `last_run_failed` | 最近一次流水线步骤是否失败 |
| `trends_demo_active` | 为 true 时首页/Trends 页显示「Trends 为演示数据」 |
| `weekly_demo_active` | 为 true 时首页隐藏周榜区块（fixture/历史不足） |

页眉文案 **数据更新于 …（香港）** 只读 `meta.json`，不用浏览器当前时间。

### 周榜算法（步骤 E）【估】

- **何时**：香港时间周一，或 `raw/trends_*.json` 跨度 ≥6 天；否则使用 `fixtures/weekly_movers_demo.json`（`skipped: insufficient_history`）。
- **词条 Top10**：`growth_score = interest_now − interest_prev`（约 7 天前最近快照 vs 最新快照，种子词 + 默认 geo）；若本周 Trends 以 demo 为主则整批 disqualify。
- **应用 Top10**：`rank_delta < 0` 名次上升优先，`growth_score = -rank_delta`；**本周新进**单独列表（`new_entry`，最多 10）。
- 产出：`data/weekly_movers.json`、`raw/weekly_YYYYWww.json`、首页「本周增长最快」两 Tab（词条 | 应用）+ 新进。

## 如何改种子词

编辑 **`config/seeds.json`**（无需改代码）：

- `keywords[]`：每项 `keyword` + `track`（赛道）；接单检索词可加可选 `heat`：`hot` | `cold`（长尾）
- **接单帖检索**：`scripts/ingest_job_leads` 读取上述赛道（建站/预约接入/预约+支付/AI 加固/AI 客服/Agent/本地 Agent 工作流/代码修复/复杂集成），按赛道轮询选取 query，并写入 `data/job_search_keywords.json` 与 `public/data/job_search_keywords.json`；**接单帖页** `jobs.html`「搜索词库」面板展示同一文件
- 主提案种子勿用宽网词（如 `booking system`、`online booking`、`appointment scheduling` 裸词）；预约+支付赛道见 `booking_keywords_daily` 草案说明
- `default_geo` / `additional_geos`：地区，默认 US，可加 GB/CA/AU/SG
- `fetch_additional_geos`：设为 `true` 时每日同时拉取 `additional_geos`（默认 `false`，避免请求过多）
- `window_primary_days`：Trends 时间窗（默认 90 天）

规格中的 v1 全量种子词已预置。

## CSV 排行上传（可选）

将导出文件放到 **`uploads/rankings*.csv`**，表头示例：

```csv
name,url,source,rank_now,category_tags
My Product,https://...,manual_csv,5,AI|SaaS
```

`category_tags` 用 `|` 分隔。样例：`uploads/rankings_sample.csv`。

若 Product Hunt 在 CI 被限流，请用 CSV 并在 Runs 中查看 `ph_failed` / 错误信息。

若 Google Trends 在 Actions IP 上返回 400/429，workflow 默认设 `TRENDS_FALLBACK_DEMO=1`： live 失败时自动用 `fixtures/trends_demo.json`，并在 Runs 标 `trends_fallback_demo`。

## 数据字段说明

### Trends（`data/trends_daily.json`）

| 字段 | 说明 |
|------|------|
| `keyword` / `geo` / `window` | 词、地区、时间窗 |
| `interest_now` | Google 相对热度 0–100 |
| `slope_90d` | 上升/持平/下降【估】 |
| `related_queries` | 上升相关查询（最多 10） |
| `pay_intent_score` | 0–3 付费意图启发式【估】 |
| `fetched_at` | 香港时间 |

### 排行（`data/rankings_delta.json`）

| 字段 | 说明 |
|------|------|
| `name` / `url` / `source` | 产品、链接、来源 |
| `rank_now` / `rank_prev` / `rank_delta` | 名次与变化 |
| `signal_note` | 涨/掉/新进榜 一句话 |
| `category_tags` | 品类标签 |

### 机会卡（`data/opportunities.json`）

| 字段 | 说明 |
|------|------|
| `title` / `track` | 标题、赛道 |
| `trends_hit` / `ranking_hit` | yes/no |
| `pay_intent_score` | 排序用【估】 |
| `verdict` | 做 / 观察 / 否（规则初判，可人工改） |
| `action` / `cost` / `boundary` / `verify` | 详情四段 |
| `skill_fit` | 软件交付 / 信息整理 / 自动化 / 落不上 |
| `verdict_manual` | `true` 时流水线不覆盖 `verdict` 与四段 |

人工改判定：在 JSON 里改 `verdict`，并设 `"verdict_manual": true` 与可选 `reviewer` / `last_reviewed_at`。

### Runs（`data/runs.json`）

每次步骤的 `run_id`、时间、`status`（success/partial/failed）、`counts`、`error`。

### 站点 meta（`public/data/meta.json`）

全站刷新时间与调度字段，供页眉与 Runs 页引用。

原始 JSON 在 `raw/` 保留约 **30 天**（自动清理）。

### 合并后验证预览

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://gaopfEditer.github.io/requirement-trendradar/
```

期望 **200**；合并触发 `deploy-pages.yml` 或跑完 Pipeline 后部署。

## 本地预览静态站

```bash
python -m scripts.run_pipeline --demo
cd public && python -m http.server 8080
```

浏览器打开 http://localhost:8080/

## 明确不做（v1）

- 自动投标 / 自动发帖  
- 绕登录爬付费 SEO 站  
- 复杂权限后台  

## 技术栈

- Python 3.12 + [pytrends](https://github.com/GeneralMills/pytrends)（Google Trends 公开接口）
- 静态 HTML/JS，GitHub Pages 部署

## 许可

内部工具，按仓库所有者约定使用。
