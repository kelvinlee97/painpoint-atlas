import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .storage import Database


def _json_for_html(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def load_dashboard_payload(path: str) -> dict:
    database = Database(path)
    try:
        apps = {f"{item.store}:{item.external_id}": item for item in database.get_apps()}
        reviews = {
            f"{item.store}:{item.external_id}": item
            for item in database.get_reviews()
        }
        evidence = {item.review_id: item for item in database.get_evidence()}
        rows = database.connection.execute(
            """
            SELECT label, summary, affected_user, validation_action, evidence_ids,
                   score, review_count, app_count, average_severity,
                   average_paid_signal, failure_stage, root_cause,
                   user_consequence, commercial_implication, decision,
                   analysis_confidence
            FROM opportunities ORDER BY score DESC
            """
        ).fetchall()
        opportunities = []
        for row in rows:
            (
                label, summary, affected_user, validation_action, ids_json,
                score, review_count, app_count, average_severity,
                average_paid_signal, failure_stage, root_cause,
                user_consequence, commercial_implication, decision,
                analysis_confidence,
            ) = row
            app_rows = {}
            evidence_rows = []
            for evidence_id in json.loads(ids_json):
                item = evidence.get(evidence_id)
                review = reviews.get(evidence_id)
                if not item or not review:
                    continue
                app = apps.get(f"{review.store}:{review.app_external_id}")
                if app:
                    app_rows[f"{app.store}:{app.external_id}"] = {
                        "name": app.name,
                        "category": app.category,
                        "description": app.description,
                        "developer": app.developer,
                        "price": app.price,
                        "url": app.url,
                    }
                evidence_rows.append(
                    {
                        "app_name": app.name if app else review.app_external_id,
                        "store": review.store,
                        "rating": review.rating,
                        "quote": item.quote,
                        "source_url": review.source_url,
                    }
                )
            opportunities.append(
                {
                    "label": label,
                    "summary": summary,
                    "affected_user": affected_user,
                    "validation_action": validation_action,
                    "score": score,
                    "review_count": review_count,
                    "app_count": app_count,
                    "average_severity": average_severity,
                    "average_paid_signal": average_paid_signal,
                    "failure_stage": failure_stage,
                    "root_cause": root_cause,
                    "user_consequence": user_consequence,
                    "commercial_implication": commercial_implication,
                    "decision": decision,
                    "analysis_confidence": analysis_confidence,
                    "apps": list(app_rows.values()),
                    "evidence": evidence_rows,
                }
            )
        return {
            "summary": {
                "apps": database.count_apps(),
                "reviews": database.count_reviews(),
                "evidence": database.count_evidence(),
                "opportunities": database.count_opportunities(),
            },
            "opportunities": opportunities,
        }
    finally:
        database.close()


def render_dashboard(payload: dict) -> str:
    data = _json_for_html(payload)
    return f'''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opportunity Radar</title>
<style>
:root {{ color-scheme: light; --ink:#172033; --muted:#667085; --line:#e5e7eb; --panel:#fff; --bg:#f6f7fb; --accent:#635bff; --soft:#eeecff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,sans-serif; }} main {{ max-width:1240px; margin:auto; padding:32px 20px 64px; }} h1 {{ font-size:32px; margin:0 0 6px; }} h2 {{ font-size:19px; margin:0 0 4px; }} h3 {{ margin:0; }} a {{ color:var(--accent); }} .muted,.caption {{ color:var(--muted); }}
.header {{ margin-bottom:24px; }} .eyebrow {{ color:var(--accent); font-weight:700; letter-spacing:.08em; text-transform:uppercase; font-size:12px; }} .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }} .metric,.panel,.card {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:0 5px 20px #1018280a; }} .metric {{ padding:18px; }} .metric strong {{ display:block; font-size:28px; margin-top:5px; }} .panel,.card {{ padding:20px; margin-bottom:20px; }}
.controls {{ display:flex; gap:12px; margin-top:16px; }} input,select {{ border:1px solid var(--line); border-radius:10px; padding:10px 12px; font:inherit; background:white; }} input {{ flex:1; min-width:240px; }} .ranking {{ display:grid; gap:10px; margin-top:16px; }} .rank {{ display:grid; grid-template-columns:minmax(180px,1fr) 2fr 70px; gap:12px; align-items:center; }} .bar {{ height:10px; background:var(--soft); border-radius:999px; overflow:hidden; }} .bar i {{ display:block; height:100%; background:var(--accent); }} .score {{ text-align:right; font-weight:700; }}
.card-head {{ display:flex; justify-content:space-between; gap:20px; }} .decision {{ background:var(--soft); color:#4138a8; border-radius:999px; padding:5px 10px; white-space:nowrap; }} .facts {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0 18px; }} .fact {{ background:#f8fafc; border:1px solid var(--line); border-radius:8px; padding:5px 9px; color:var(--muted); }} .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }} .section {{ border-top:1px solid var(--line); padding-top:14px; margin-top:14px; }} .section strong {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }} .app,.quote {{ border-left:3px solid var(--soft); padding:8px 12px; background:#fafbff; margin-top:8px; }} .quote {{ font-size:14px; }} .empty {{ padding:24px; color:var(--muted); text-align:center; }}
@media (max-width:760px) {{ main {{ padding:22px 14px 48px; }} .summary {{ grid-template-columns:repeat(2,1fr); }} .grid {{ grid-template-columns:1fr; }} .card-head {{ display:block; }} .decision {{ display:inline-block; margin-top:12px; }} .controls {{ display:block; }} input,select {{ width:100%; margin-bottom:8px; }} .rank {{ grid-template-columns:1fr 1fr 55px; }} }}
</style></head>
<body><main>
<header class="header"><div class="eyebrow">Local market intelligence</div><h1>Opportunity Radar</h1><p class="muted">从差评追踪失败链路、商业风险和可验证机会。</p></header>
<section class="summary" id="summary"></section>
<section class="panel"><h2>机会优先级</h2><p class="caption">按综合优先级排序；不是收入预测。</p><div class="ranking" id="ranking"></div></section>
<section class="panel"><h2>机会解剖</h2><div class="controls"><input id="search" placeholder="搜索问题、App、根因或商业判断"><select id="decision"><option value="">全部判断</option><option>值得优先验证</option><option>优先作为避坑规则</option><option>暂不进入</option></select></div></section>
<section id="cards"></section>
</main>
<script>
const DATA = {data};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
const storeName = value => value === 'app_store' ? 'Apple App Store' : 'Google Play';
function render() {{
  const s = DATA.summary;
  document.querySelector('#summary').innerHTML = [['App',s.apps],['评论',s.reviews],['证据',s.evidence],['机会',s.opportunities]].map(x => `<div class="metric"><span class="muted">${{x[0]}}</span><strong>${{x[1]}}</strong></div>`).join('');
  const q = document.querySelector('#search').value.trim().toLowerCase();
  const d = document.querySelector('#decision').value;
  const items = DATA.opportunities.filter(item => (!q || JSON.stringify(item).toLowerCase().includes(q)) && (!d || item.decision === d));
  document.querySelector('#ranking').innerHTML = items.length ? items.map(item => `<div class="rank"><span>${{esc(item.label)}}</span><div class="bar"><i style="width:${{Math.min(100,Math.max(0,item.score))}}%"></i></div><span class="score">${{Number(item.score).toFixed(1)}}</span></div>`).join('') : '<div class="empty">没有匹配的机会。</div>';
  document.querySelector('#cards').innerHTML = items.length ? items.map(item => `<article class="card"><div class="card-head"><div><h3>${{esc(item.label)}}</h3><p class="muted">${{esc(item.summary)}}</p></div><span class="decision">${{esc(item.decision || '待补充')}}</span></div><div class="facts"><span class="fact">优先级 ${{Number(item.score).toFixed(1)}}</span><span class="fact">${{item.review_count}} 条评论 / ${{item.app_count}} 个 App</span><span class="fact">严重度 ${{Number(item.average_severity).toFixed(1)}}/5</span><span class="fact">付费信号 ${{Number(item.average_paid_signal).toFixed(1)}}/3</span></div><div class="grid"><div class="section"><strong>失败阶段</strong>${{esc(item.failure_stage || '待补充')}}</div><div class="section"><strong>根因判断</strong>${{esc(item.root_cause || '待补充')}}</div><div class="section"><strong>用户后果</strong>${{esc(item.user_consequence || '待补充')}}</div><div class="section"><strong>商业判断</strong>${{esc(item.commercial_implication || '待补充')}}</div><div class="section"><strong>验证动作</strong>${{esc(item.validation_action)}}</div><div class="section"><strong>分析置信度</strong>${{Number(item.analysis_confidence || 0).toFixed(2)}}</div></div><div class="section"><strong>涉及产品</strong>${{item.apps.map(app => `<div class="app"><b>${{esc(app.name)}}</b> · ${{esc(app.category)}}<br><span class="muted">${{esc(app.description || '商店页未提供可核验的产品描述。')}}</span></div>`).join('')}}</div><div class="section"><strong>原始证据</strong>${{item.evidence.map(row => `<div class="quote"><b>${{esc(row.app_name)}} · ${{esc(storeName(row.store))}} · ${{row.rating}}★</b> — ${{esc(row.quote)}} <a href="${{esc(row.source_url)}}" target="_blank" rel="noreferrer">来源</a></div>`).join('')}}</div></article>`).join('') : '<div class="empty">没有可展示的机会。先运行 run 生成分析。</div>';
}}
document.querySelector('#search').addEventListener('input', render); document.querySelector('#decision').addEventListener('change', render); render();
</script></body></html>'''


def write_static_dashboard(database_path: str, output_dir: str | Path) -> Path:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    output = target / "index.html"
    output.write_text(
        render_dashboard(load_dashboard_payload(database_path)),
        encoding="utf-8",
    )
    return output


def serve_dashboard(path: str, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = b'{"ok":true}'
                content_type = "application/json"
            else:
                body = render_dashboard(load_dashboard_payload(path)).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard 已启动：http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
