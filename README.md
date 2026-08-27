# Painpoint Atlas

Painpoint Atlas 是一个本地优先、可持续刷新的市场情报工具：从 Apple App Store 和 Google Play 的公开应用页收集 1–3 星评论，把用户抱怨拆成可核验的失败原因，再形成可测试的商业机会。

它服务的不是“评论摘要”，而是机会判断：什么产品、服务谁、在哪个环节失败、造成什么用户代价、谁可能付费，以及下一步如何用访谈、原型、落地页或试点验证。

## 分析关系链

```text
公开应用页
  → App 与 1–3 星评论
  → 逐条证据抽取（痛点、场景、严重度、付费信号、原文引证）
  → 跨 App 问题聚类
  → 机会门槛与启发式优先级排序
  → 失败链路、根因、用户后果和商业判断
  → SQLite、中文 Markdown 报告和 Dashboard
```

当前实现的数据源只有 Apple App Store 和 Google Play，覆盖 productivity、business、AI utilities 三类发现入口。社交平台痛点和创业失败案例尚未接入，不应把当前报告描述成全网舆情或完整创业失败数据库。

## 结果口径

- 机会主榜要求至少 **3 条评论**，并覆盖至少 **2 个 App**。
- `paid_signal` 是评论中出现付款、取消、迁移或具体替代方案等信号，不等于真实支付意愿。
- 机会分数是 0–100 的固定启发式优先级：跨产品覆盖 25%、每 App 证据频率 25%、严重度 20%、新近度 15%、付费信号 15%；不是市场规模或收入预测。
- 聚类默认最多使用 40 条受控证据，格式校验失败时降到 20 条、再到 10 条重试；这是可靠性边界，不代表全库证据都被一次聚类。
- 商店未提供产品描述时，报告会明确标记缺失，不让模型猜测产品定位。

## Requirements

- Python 3.11+
- 一个可用的 OpenAI API key
- 项目使用 Python 标准库，不需要额外安装依赖

## 本地运行

在仓库根目录执行。先验证两个公开来源：

```bash
python3 -m opportunity_radar probe-sources
```

再配置模型并运行完整管线。`OPENAI_MODEL` 在本地是必填项；下面的值是当前 GitHub Actions 的默认配置，前提是你的 API 账户或网关支持它。

```bash
export OPENAI_API_KEY='你的 key'
export OPENAI_MODEL='gpt-5.6-luna'
python3 -m opportunity_radar run
```

默认输出：

- 增量数据库：`data/opportunity_radar.sqlite3`
- 中文报告：`reports/YYYY-MM-DD.md`

产品品牌是 `Painpoint Atlas`；Python 包名、命令入口和 SQLite 文件名暂时沿用 `opportunity_radar`，以保持已有命令和增量数据兼容。

## Dashboard

启动只监听回环地址的本地 Dashboard：

```bash
python3 -m opportunity_radar dashboard
```

打开 <http://127.0.0.1:8000>。页面展示机会排名、App 用途、失败阶段、根因、用户后果、商业判断、验证动作和原始差评证据。重新运行 `run` 后刷新页面即可看到最新数据库内容；服务不会监听公网地址。

生成不依赖 Python 服务的静态版本：

```bash
python3 -m opportunity_radar build-pages
```

输出为 `site/index.html`，既可本地预览，也可作为 GitHub Pages artifact 发布。

## GitHub Pages 持续更新

`.github/workflows/refresh-pages.yml` 会：

1. 在 `main` 上运行测试。
2. 用 `OPENAI_API_KEY` 和 `OPENAI_MODEL` 运行采集与分析。
3. 生成 SQLite 增量状态、当天 Markdown 报告和静态 Dashboard。
4. 将数据库与报告提交到一次性自动化分支，创建并 squash 合并 PR，再部署 `site/` 到 GitHub Pages。

默认每天 **02:30 UTC** 运行，也可以手动触发。

首次配置：

1. Settings → Pages → Source 选择 **GitHub Actions**。
2. Settings → Secrets and variables → Actions → Repository secrets，创建 `OPENAI_API_KEY`。
3. 在 Variables 创建 `OPENAI_MODEL`；不创建时，工作流使用 `gpt-5.6-luna`。
4. Actions → **Refresh and deploy Painpoint Atlas** → Run workflow。

工作流只允许在 `main` 上运行带 key 的刷新步骤。刷新状态通过自动化 PR 写回，不绕过 `main` 的 PR、禁止删除和禁止强制推送等保护规则。

### Secret 安全配置

不要把 key 写入代码、报告、SQLite、GitHub Variables、issue 或聊天内容。GitHub CLI 配置时通过隐藏输入传递：

```bash
gh auth status
read -rsp "Paste OpenAI API key: " ATLAS_KEY; printf '\n'
printf %s "$ATLAS_KEY" | gh secret set OPENAI_API_KEY --repo kelvinlee97/painpoint-atlas
unset ATLAS_KEY
gh variable set OPENAI_MODEL --body gpt-5.6-luna --repo kelvinlee97/painpoint-atlas
```

本地运行建议使用权限收紧的用户目录文件，不要放入 `~/.bashrc`：

```bash
mkdir -p ~/.config/painpoint-atlas
chmod 700 ~/.config/painpoint-atlas
nano ~/.config/painpoint-atlas/env
chmod 600 ~/.config/painpoint-atlas/env
set -a; source ~/.config/painpoint-atlas/env; set +a
python3 -m opportunity_radar run
unset OPENAI_API_KEY OPENAI_MODEL
```

文件内容只放本机自己的值：

```bash
export OPENAI_API_KEY='在这里粘贴 key'
export OPENAI_MODEL='gpt-5.6-luna'
```

如果 key 曾经进入聊天、shell 历史或配置文件，应先撤销并生成新 key，再更新 GitHub Secret；仅删除文件不能让已经暴露的 key 失效。

## 代码与输出对应关系

| 部分 | 责任 |
| --- | --- |
| `opportunity_radar/sources.py` | 发现 App、抓取低星评论、读取产品元数据 |
| `opportunity_radar/analysis.py` | 提取带原文引证的证据、聚类、生成战略分析 |
| `opportunity_radar/scoring.py` | 应用机会门槛和固定优先级公式 |
| `opportunity_radar/storage.py` | 保存 App、评论、证据、机会和运行状态 |
| `opportunity_radar/report.py` | 生成中文 Markdown 分析报告 |
| `opportunity_radar/dashboard.py` | 生成本地与静态 HTML Dashboard |
| `.github/workflows/refresh-pages.yml` | 测试、刷新、通过自动化 PR 持久化状态并部署 Pages |

## 公开数据与限制

仓库和 GitHub Pages 是公开的；工作流提交的 SQLite、报告和静态页面会公开应用元数据、评论文本片段及模型分析。写入数据库、报告和页面前会执行启发式的邮箱、手机号、URL、账号和常见密钥样式脱敏，但它不能保证匿名化，也没有自动保留期限策略；发布前仍应评估公开这些内容是否合适。评论数量不能直接代表市场规模，模型分析也不能替代用户访谈和付费验证。

Apple 使用公开 Search API 与 RSS 评论源，Google 使用公开分类页与应用详情页；适配器保持独立，以便页面结构变化时单独调整。当前数据库保存评论标题、正文、评分、时间、版本和来源链接，不保存作者或设备字段。

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## License

仓库目前没有 `LICENSE` 文件。它可以公开浏览，但在添加明确许可证之前，不应默认认为代码允许自由再发布或商用。
