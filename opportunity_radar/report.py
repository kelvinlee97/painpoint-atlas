from datetime import date
from pathlib import Path

from .models import App, Evidence, Opportunity, Review


def _shorten(text: str, limit: int = 280) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_report(
    opportunities: list[Opportunity],
    evidence: dict[str, Evidence],
    reviews: dict[str, Review],
    apps: dict[str, App] | None = None,
    *,
    generated_at: str | None = None,
    clustered_evidence_count: int | None = None,
) -> str:
    generated_at = generated_at or date.today().isoformat()
    apps = apps or {}
    lines = [
        "# Opportunity Radar：失败原因与商业机会分析",
        "",
        f"> 生成日期：{generated_at}  ",
        "> 分析对象：应用商店公开低评分评论；机会分数是优先级信号，不是收入预测。",
        "",
    ]
    if clustered_evidence_count is not None:
        lines[2:2] = [
            f"> 本次聚类分析证据：{clustered_evidence_count} 条；数据库已采集：{len(evidence)} 条。",
            "> 聚类采用受控样本以保证证据 ID 完整；扩大到全库前需要分批合并校验。",
            "",
        ]
    if not opportunities:
        lines.append("暂无达到主榜门槛的机会。")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "## Executive Summary",
            "",
            f"- **当前最值得验证的方向**：{opportunities[0].label}，优先级分数 "
            f"{opportunities[0].score:.2f}，覆盖 {opportunities[0].app_count} 个 App。",
            f"- **证据强度**：主榜共 {len(opportunities)} 个机会，均满足至少 3 条评论、"
            "至少 2 个 App 的交叉验证门槛。",
            "- **商业含义**：评论反映的是已发生的失败与流失信号，不等于市场规模；"
            "下一步必须用访谈、落地页或付费试点验证需求是否可转化。",
            "",
        ]
    )

    for index, opportunity in enumerate(opportunities, start=1):
        app_records = {}
        for evidence_id in opportunity.evidence_ids:
            review = reviews[evidence_id]
            key = f"{review.store}:{review.app_external_id}"
            if key in app_records:
                continue
            app_records[key] = apps.get(key)
        lines.extend(
            [
                f"## {index}. {opportunity.label} — {opportunity.score:.2f}",
                "",
                f"**决策结论**：{opportunity.decision or '待补充'}",
                f"**问题概述**：{opportunity.summary}",
                f"**受影响用户**：{opportunity.affected_user}",
                f"**证据规模**：{opportunity.review_count} 条评论 / {opportunity.app_count} 个应用",
                f"**平均严重度**：{opportunity.average_severity:.2f}/5；"
                f" **平均付费信号**：{opportunity.average_paid_signal:.2f}/3",
                "",
                "### 涉及产品：它们是什么、服务谁",
                "",
            ]
        )
        for app in app_records.values():
            if not app:
                lines.append("- 产品元数据未匹配；报告不对 App 用途做推测。")
                continue
            store = "Apple App Store" if app.store == "app_store" else "Google Play"
            description = app.description or "商店页未提供可核验的产品描述。"
            details = [f"{app.name}（{store}，{app.category}）"]
            if app.developer:
                details.append(f"开发者：{app.developer}")
            if app.price:
                details.append(f"价格：{app.price}")
            lines.append(f"- **{'；'.join(details)}**")
            lines.append(f"  - 产品用途：{_shorten(description, 240)}")
            lines.append(f"  - 产品链接：{app.url}")
        lines.extend(
            [
                "",
                "### 失败链路与归因",
                "",
                f"- **失败阶段**：{opportunity.failure_stage or '待补充'}",
                f"- **根因判断**：{opportunity.root_cause or '待补充'}",
                f"- **用户后果**：{opportunity.user_consequence or '待补充'}",
                "",
                "### 商业判断",
                "",
                f"- **商业价值**：{opportunity.commercial_implication or '待补充'}",
                f"- **验证动作**：{opportunity.validation_action}",
                f"- **分析置信度**：{opportunity.analysis_confidence:.2f}",
                "",
                "### 观察到的证据",
                "",
            ]
        )
        for evidence_id in opportunity.evidence_ids:
            item = evidence[evidence_id]
            review = reviews[evidence_id]
            store = "Apple App Store" if review.store == "app_store" else "Google Play"
            app = apps.get(f"{review.store}:{review.app_external_id}")
            app_name = app.name if app else review.app_external_id
            lines.append(
                f"- [{app_name} · {store}，{review.rating}★]({review.source_url}) "
                f"— {_shorten(item.quote)}"
            )
        lines.append("")
    lines.extend(
        [
            "## 进一步验证问题",
            "",
            "- 哪些问题会让用户真正取消订阅、退款或迁移，而不是只留下低分？",
            "- 受影响用户是否能被明确定位并触达，还是只存在于极少数边缘场景？",
            "- 解决方案能否在两周内用人工服务、原型或落地页验证，而不必先做完整产品？",
            "",
            "## 口径与限制",
            "",
            "- App 数量、评论数量来自公开商店页面；评论量不能直接代表市场规模。",
            "- 商店没有提供产品描述时，报告会显示缺失，不用模型猜测产品定位。",
            "- 商业判断是基于评论证据的研究假设，必须通过真实用户和付费行为继续验证。",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
