# Opportunity Radar

个人本地机会雷达：从 Apple App Store 和 Google Play 的公开应用页中发现软件/AI 工具，收集 1–3 星评论，提取痛点并生成中文 Markdown 简报。

## Requirements

- Python 3.11+
- 一个可用的 OpenAI API key

## Run

先验证两边来源：

```bash
python3 -m opportunity_radar probe-sources
```

配置模型分析：

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='your-model-id'
python3 -m opportunity_radar run
```

默认生成：

- SQLite：`data/opportunity_radar.sqlite3`
- 简报：`reports/YYYY-MM-DD.md`

启动本地可视化 Dashboard（只监听本机，不部署公网）：

```bash
python3 -m opportunity_radar dashboard
```

然后打开 <http://127.0.0.1:8000>。Dashboard 会展示机会优先级、涉及的 App 及用途、失败阶段、根因、用户后果、商业判断、验证动作和原始差评证据；重新运行 `run` 后刷新页面即可看到新结果。

## GitHub Pages 持续更新

生成一次不依赖 Python 服务的静态 Dashboard：

```bash
python3 -m opportunity_radar build-pages
```

输出文件为 `site/index.html`，可作为 GitHub Pages artifact 发布。`.github/workflows/refresh-pages.yml` 已配置为每天 UTC 02:30、或手动触发一次 `run`、生成静态 Dashboard 并部署。

在 GitHub 仓库中完成一次配置：

1. Settings → Pages → Source 选择 **GitHub Actions**。
2. Settings → Secrets and variables → Actions → New repository secret，名称填 `OPENAI_API_KEY`。
3. 同一页的 Variables 添加 `OPENAI_MODEL`；不添加时默认使用 `gpt-5.6-luna`。
4. Actions → Refresh and deploy Opportunity Radar → Run workflow。

工作流会提交 `data/opportunity_radar.sqlite3` 和当天报告来保存增量状态；本仓库公开后，这些采集数据和分析报告也会公开。当前提交和 SQLite 快照不包含 API key；不要把真实 key 写入代码、报告或静态页面，只通过 GitHub Actions Secret 配置。

`run` 会在分析前重新执行来源探针。来源探针失败或缺少 API 配置时会停止，不会生成无证据报告。

报告不是泛化的痛点汇总：每个机会都要求至少 3 条评论、至少 2 个 App 的交叉证据，并把评论信号拆成失败链路、根因、用户损失和可验证的商业假设。当前数据源优先覆盖 Apple App Store 和 Google Play；社交平台与创业失败案例会在这条链路稳定后再接入。

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Apple 使用公开 Search API 的分类查询，Google 使用公开分类页；两者都只保存评论正文、评分、时间和来源链接，不保存作者或设备资料。应用商店评论 API 的官方授权边界不同，因此来源适配器保持独立，页面结构变化时只需调整对应适配器。
