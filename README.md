# 海外需求雷达 v1

把 **Google Trends 热词** 与 **Product Hunt / CSV 排行变更** 交叉成可筛选的「机会卡」，通过静态站展示。内部决策工具：不自动投标、不绕登录爬付费站。

## 预览 URL

启用 GitHub Pages（Settings → Pages → Source: **GitHub Actions**）后，站点地址为：

**https://gaopfEditer.github.io/requirement-trendradar/**

（合并本仓库并跑通一次 `Daily Demand Radar` workflow 后即可访问。）

## 流水线四步

| 步骤 | 命令 | 说明 |
|------|------|------|
| A | `python -m scripts.ingest_trends` | 读种子词 → 拉 Trends → `raw/trends_YYYYMMDD.json` + `data/trends_daily.json` |
| B | `python -m scripts.ingest_rankings` | Product Hunt 公开 Atom Feed + `uploads/rankings*.csv` → `rankings_daily` / `rankings_delta` |
| C | `python -m scripts.build_opportunity_cards` | 交叉合成机会卡，已设 `verdict_manual: true` 的不覆盖 verdict |
| D | `python -m scripts.publish_site` | 复制 JSON 到 `public/data/` 供前端读取 |

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

- Workflow：`.github/workflows/daily-radar.yml`
- 默认 **每天 09:00 香港时间**（cron `0 1 * * *` UTC）
- 手动触发：Actions → **Daily Demand Radar** → **Run workflow**
  - 可选 `demo`（fixtures）或 `csv_only`（排行回退 CSV）

## 如何改种子词

编辑 **`config/seeds.json`**（无需改代码）：

- `keywords[]`：每项 `keyword` + `track`（赛道）
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

原始 JSON 在 `raw/` 保留约 **30 天**（自动清理）。

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
