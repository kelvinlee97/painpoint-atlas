import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
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
<title>Opportunity Radar · Painpoint Atlas</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<style>
:root {{ color-scheme:light; --ink:#102a43; --text:#0f172a; --muted:#475569; --line:#dbeafe; --panel:#fff; --surface:#f8fafc; --surface-alt:#eef4fb; --primary:#1e40af; --blue:#3b82f6; --amber:#d97706; --amber-bg:#fff7ed; --soft-blue:#eff6ff; --ring:#1e40af; }}
* {{ box-sizing:border-box; }} html {{ scroll-behavior:smooth; }} body {{ margin:0; background:var(--surface); color:var(--text); font:15px/1.6 "Fira Sans",ui-sans-serif,system-ui,sans-serif; overflow-x:hidden; }} body,button,input,select {{ -webkit-font-smoothing:antialiased; }} main {{ max-width:1240px; margin:auto; padding:28px 24px 72px; }} h1,h2,h3,p {{ margin-top:0; }} h1 {{ color:var(--ink); font-size:clamp(28px,4vw,42px); letter-spacing:-.035em; line-height:1.1; margin-bottom:10px; }} h2 {{ color:var(--ink); font-size:20px; letter-spacing:-.015em; margin-bottom:4px; }} h3 {{ color:var(--ink); font-size:20px; line-height:1.25; margin-bottom:6px; }} a {{ color:var(--primary); font-weight:650; }} .muted,.caption,.helper {{ color:var(--muted); }}
.skip-link {{ position:absolute; left:16px; top:12px; z-index:5; padding:10px 14px; background:var(--ink); color:#fff; border-radius:8px; transform:translateY(-160%); transition:transform .15s ease; }} .skip-link:focus {{ transform:translateY(0); }}
.masthead {{ display:flex; justify-content:space-between; gap:28px; align-items:flex-end; padding:12px 0 26px; margin-bottom:20px; border-bottom:1px solid var(--line); }} .eyebrow {{ color:var(--primary); font-family:"Fira Code",ui-monospace,monospace; font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin-bottom:10px; }} .lead {{ max-width:720px; color:var(--muted); font-size:16px; margin-bottom:0; }} .meta {{ flex:0 0 auto; text-align:right; color:var(--muted); font-size:13px; }} .meta strong {{ display:block; color:var(--ink); font-family:"Fira Code",ui-monospace,monospace; font-size:12px; letter-spacing:.05em; margin-bottom:5px; }}
.summary {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:20px; }} .metric,.panel,.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; }} .metric {{ min-height:120px; padding:17px 18px; border-top:3px solid var(--blue); }} .metric-label {{ color:var(--muted); font-size:13px; font-weight:650; }} .metric strong {{ display:block; color:var(--ink); font-family:"Fira Code",ui-monospace,monospace; font-size:29px; letter-spacing:-.05em; line-height:1.1; margin:11px 0 7px; }} .metric-note {{ color:var(--muted); font-size:12px; }} .panel,.card {{ padding:22px; margin-bottom:20px; }} .section-heading {{ display:flex; justify-content:space-between; gap:16px; align-items:baseline; }} .caption {{ font-size:13px; margin-bottom:0; }}
.ranking {{ list-style:none; display:grid; gap:2px; margin:14px 0 0; padding:0; }} .rank {{ display:grid; grid-template-columns:minmax(210px,1.15fr) minmax(160px,2fr) 76px; gap:14px; align-items:center; padding:10px 0; border-top:1px solid #eff6ff; }} .rank:first-child {{ border-top:0; }} .rank-name {{ display:flex; min-width:0; align-items:center; gap:10px; }} .rank-name strong {{ min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }} .rank-index {{ color:var(--blue); font-family:"Fira Code",ui-monospace,monospace; font-size:12px; font-weight:700; }} .rank-track {{ height:10px; background:var(--soft-blue); border-radius:999px; overflow:hidden; }} .rank-track span {{ display:block; height:100%; min-width:2px; background:linear-gradient(90deg,var(--primary),var(--blue)); border-radius:999px; }} .score {{ color:var(--ink); font-family:"Fira Code",ui-monospace,monospace; font-size:13px; font-weight:700; text-align:right; }}
.toolbar {{ display:grid; grid-template-columns:minmax(0,1fr) 220px auto; gap:12px; align-items:end; margin-top:17px; padding:14px; background:var(--surface-alt); border:1px solid var(--line); border-radius:10px; }} .field {{ min-width:0; }} .field label {{ display:block; color:var(--ink); font-size:12px; font-weight:700; margin:0 0 5px; }} input,select,button {{ min-height:44px; border:1px solid #bfd3eb; border-radius:8px; padding:10px 12px; font:inherit; background:#fff; color:var(--text); }} input {{ width:100%; }} input::placeholder {{ color:#64748b; }} button {{ cursor:pointer; font-weight:700; }} button:hover:not(:disabled) {{ border-color:var(--primary); background:var(--soft-blue); }} button:disabled {{ cursor:not-allowed; opacity:.5; }} .reset-button {{ white-space:nowrap; }} .helper {{ font-size:12px; margin:6px 0 0; }} .result-count {{ color:var(--ink); font-size:13px; font-weight:700; margin:13px 0 0; }}
.cards {{ display:grid; gap:16px; }} .card {{ padding:22px 22px 18px; border-left:4px solid var(--primary); }} .card-head {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; align-items:start; }} .card-kicker {{ color:var(--primary); font-family:"Fira Code",ui-monospace,monospace; font-size:11px; font-weight:700; letter-spacing:.03em; margin-bottom:8px; text-transform:uppercase; }} .card-summary {{ color:var(--muted); margin-bottom:0; }} .decision {{ display:inline-flex; align-items:center; min-height:34px; padding:6px 10px; border:1px solid transparent; border-radius:7px; font-size:13px; font-weight:750; white-space:nowrap; }} .decision-primary {{ color:#1e3a8a; background:#dbeafe; border-color:#93c5fd; }} .decision-warning {{ color:#92400e; background:var(--amber-bg); border-color:#fdba74; }} .decision-neutral {{ color:#334155; background:#f1f5f9; border-color:#cbd5e1; }} .facts {{ display:flex; flex-wrap:wrap; gap:7px; list-style:none; margin:17px 0 2px; padding:0; }} .fact {{ color:var(--muted); background:var(--surface); border:1px solid var(--line); border-radius:7px; padding:5px 9px; font-size:12px; }} .fact strong {{ color:var(--ink); font-family:"Fira Code",ui-monospace,monospace; }}
.analysis-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; margin:18px 0; background:var(--line); border:1px solid var(--line); border-radius:9px; overflow:hidden; }} .analysis-item {{ min-width:0; padding:13px 14px; background:#fff; }} .analysis-item dt {{ color:var(--muted); font-size:12px; font-weight:700; margin-bottom:4px; }} .analysis-item dd {{ color:var(--text); margin:0; overflow-wrap:anywhere; }} .disclosure {{ border-top:1px solid var(--line); }} .disclosure + .disclosure {{ margin-top:0; }} .disclosure summary {{ display:flex; justify-content:space-between; gap:12px; align-items:center; min-height:48px; color:var(--ink); cursor:pointer; font-weight:750; list-style-position:inside; }} .disclosure summary::marker {{ color:var(--primary); }} .summary-count {{ color:var(--muted); font-family:"Fira Code",ui-monospace,monospace; font-size:12px; font-weight:500; margin-left:auto; }} .details-body {{ padding:0 0 12px 22px; }} .app,.quote {{ margin-top:9px; padding:12px 14px; background:var(--surface); border:1px solid var(--line); border-left:3px solid #93c5fd; border-radius:7px; }} .app:first-child,.quote:first-child {{ margin-top:0; }} .app-name {{ margin-bottom:4px; }} .app p {{ margin:0 0 6px; }} .app-meta {{ color:var(--muted); font-size:12px; }} .quote-meta {{ display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:12px; }} .quote-meta strong {{ color:var(--ink); }} .rating {{ color:var(--amber); font-family:"Fira Code",ui-monospace,monospace; font-weight:700; white-space:nowrap; }} blockquote {{ margin:7px 0 8px; color:var(--text); }} .empty {{ padding:28px 12px; color:var(--muted); text-align:center; }}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible {{ outline:3px solid var(--ring); outline-offset:2px; }}
@media (max-width:820px) {{ main {{ padding:22px 16px 56px; }} .masthead {{ display:block; }} .meta {{ margin-top:16px; text-align:left; }} .summary {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .toolbar {{ grid-template-columns:1fr 1fr; }} .field-search {{ grid-column:1 / -1; }} .reset-button {{ width:100%; }} .analysis-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
@media (max-width:560px) {{ .summary {{ gap:8px; }} .metric {{ min-height:105px; padding:14px; }} .metric strong {{ font-size:23px; }} .panel,.card {{ padding:17px 15px; }} .toolbar,.analysis-grid {{ grid-template-columns:1fr; }} .field-search {{ grid-column:auto; }} .card-head {{ display:block; }} .decision {{ margin-top:13px; }} .rank {{ grid-template-columns:minmax(0,1fr) 58px; gap:8px; }} .rank-track {{ grid-column:1 / -1; grid-row:2; }} .score {{ grid-column:2; grid-row:1; }} .details-body {{ padding-left:0; }} }}
@media (prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ scroll-behavior:auto !important; animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; }} }}
</style></head>
<body><a class="skip-link" href="#opportunity-list">跳到机会列表</a><main>
<header class="masthead"><div><div class="eyebrow">Painpoint Atlas / Market intelligence</div><h1>Opportunity Radar</h1><p class="lead">把 App Store 与 Google Play 的差评，拆成失败链路、用户代价和可验证的商业判断。</p></div><div class="meta"><strong>LOCAL SNAPSHOT</strong><span>数据用于问题发现，不等同于收入预测</span></div></header>
<section class="summary" id="summary" aria-label="数据摘要"></section>
<section class="panel" aria-labelledby="ranking-title"><div class="section-heading"><div><h2 id="ranking-title">机会优先级</h2><p class="caption">按证据覆盖、严重度、付费信号和跨产品重复度排序。</p></div><span class="caption" id="ranking-scope">全部</span></div><ol class="ranking" id="ranking" aria-label="机会优先级排行榜"></ol></section>
<section class="panel" aria-labelledby="filters-title"><h2 id="filters-title">机会解剖</h2><p class="caption">先定位问题，再阅读证据与商业判断；长内容默认收起。</p><div class="toolbar"><div class="field field-search"><label for="search">查找证据</label><input id="search" type="search" placeholder="搜索问题、App、根因或商业判断" aria-describedby="search-help" autocomplete="off"><p class="helper" id="search-help">搜索会同时匹配机会标题、分析字段和来源 App。</p></div><div class="field"><label for="decision">商业判断</label><select id="decision"><option value="">全部判断</option><option>值得优先验证</option><option>优先作为避坑规则</option><option>暂不进入</option></select></div><button class="reset-button" id="reset" type="button">清除筛选</button></div><p class="result-count" id="result-count" aria-live="polite"></p></section>
<section class="cards" id="opportunity-list" aria-label="机会列表"></section>
</main>
<script>
const DATA = {data};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
const safeHttpUrl = value => /^https?:\\/\\//i.test(String(value || '')) ? String(value) : '';
const number = value => Number(value || 0);
const count = value => new Intl.NumberFormat('zh-CN').format(number(value));
const scoreWidth = value => Math.min(100, Math.max(0, number(value)));
const storeName = value => value === 'app_store' ? 'Apple App Store' : value === 'google_play' ? 'Google Play' : '未知来源';
const decisionClass = value => value === '值得优先验证' ? 'decision-primary' : value === '优先作为避坑规则' ? 'decision-warning' : 'decision-neutral';
function render() {{
  const s = DATA.summary;
  document.querySelector('#summary').innerHTML = [['App',s.apps,'可核验的产品对象'],['评论',s.reviews,'低星用户反馈'],['证据',s.evidence,'进入分析的证据'],['机会',s.opportunities,'跨产品问题簇']].map(x => `<article class="metric"><span class="metric-label">${{x[0]}}</span><strong>${{count(x[1])}}</strong><span class="metric-note">${{x[2]}}</span></article>`).join('');
  const q = document.querySelector('#search').value.trim().toLowerCase();
  const d = document.querySelector('#decision').value;
  const items = DATA.opportunities.filter(item => (!q || JSON.stringify(item).toLowerCase().includes(q)) && (!d || item.decision === d));
  const hasFilters = Boolean(q || d);
  document.querySelector('#result-count').textContent = hasFilters ? `显示 ${{items.length}} / ${{DATA.opportunities.length}} 个机会` : `共 ${{items.length}} 个机会`;
  document.querySelector('#ranking-scope').textContent = hasFilters ? '筛选后' : '全部';
  document.querySelector('#reset').disabled = !hasFilters;
  document.querySelector('#ranking').innerHTML = items.length ? items.map((item, index) => {{
    const scoreValue = number(item.score);
    const width = scoreWidth(item.score);
    const label = item.label || '未命名机会';
    return `<li class="rank"><div class="rank-name"><span class="rank-index">${{String(index + 1).padStart(2,'0')}}</span><strong title="${{esc(label)}}">${{esc(label)}}</strong></div><div class="rank-track" role="progressbar" aria-label="${{esc(label + '，优先级 ' + scoreValue.toFixed(1))}}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${{width.toFixed(1)}}"><span aria-hidden="true" style="width:${{width}}%"></span></div><span class="score">${{scoreValue.toFixed(1)}}</span></li>`;
  }}).join('') : '<li class="empty">没有匹配的机会。</li>';
  document.querySelector('#opportunity-list').innerHTML = items.length ? items.map((item, index) => {{
    const apps = item.apps || [];
    const evidence = item.evidence || [];
    const decision = item.decision || '待补充';
    const appMarkup = apps.length ? apps.map(app => {{
      const url = safeHttpUrl(app.url);
      return `<article class="app"><div class="app-name"><strong>${{esc(app.name || '未命名 App')}}</strong><span class="muted"> · ${{esc(app.category || '未分类')}}</span></div><p>${{esc(app.description || '商店页未提供可核验的产品描述。')}}</p><p class="app-meta">开发者：${{esc(app.developer || '未提供')}} · 价格：${{esc(app.price || '未提供')}}</p>${{url ? `<a href="${{esc(url)}}" target="_blank" rel="noopener noreferrer">查看商店页 ↗</a>` : ''}}</article>`;
    }}).join('') : '<p class="muted">暂无关联产品。</p>';
    const evidenceMarkup = evidence.length ? evidence.map(row => {{
      const url = safeHttpUrl(row.source_url);
      return `<article class="quote"><div class="quote-meta"><strong>${{esc(row.app_name || '未知 App')}} · ${{esc(storeName(row.store))}}</strong><span class="rating">${{number(row.rating).toFixed(0)}}★</span></div><blockquote>${{esc(row.quote || '暂无引文')}}</blockquote>${{url ? `<a href="${{esc(url)}}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>` : '<span class="muted">来源链接不可用</span>'}}</article>`;
    }}).join('') : '<p class="muted">暂无原始证据。</p>';
    return `<article class="card"><div class="card-head"><div><div class="card-kicker">机会 ${{String(index + 1).padStart(2,'0')}} · 置信度 ${{number(item.analysis_confidence).toFixed(2)}}</div><h3>${{esc(item.label || '未命名机会')}}</h3><p class="card-summary">${{esc(item.summary || '暂无摘要')}}</p></div><span class="decision ${{decisionClass(decision)}}">${{esc(decision)}}</span></div><ul class="facts" aria-label="机会指标"><li class="fact"><strong>${{number(item.score).toFixed(1)}}</strong> 优先级</li><li class="fact"><strong>${{count(item.review_count)}}</strong> 条评论 / <strong>${{count(item.app_count)}}</strong> 个 App</li><li class="fact">严重度 <strong>${{number(item.average_severity).toFixed(1)}}/5</strong></li><li class="fact">付费信号 <strong>${{number(item.average_paid_signal).toFixed(1)}}/3</strong></li></ul><dl class="analysis-grid"><div class="analysis-item"><dt>失败阶段</dt><dd>${{esc(item.failure_stage || '待补充')}}</dd></div><div class="analysis-item"><dt>根因判断</dt><dd>${{esc(item.root_cause || '待补充')}}</dd></div><div class="analysis-item"><dt>用户后果</dt><dd>${{esc(item.user_consequence || '待补充')}}</dd></div><div class="analysis-item"><dt>商业判断</dt><dd>${{esc(item.commercial_implication || '待补充')}}</dd></div><div class="analysis-item"><dt>验证动作</dt><dd>${{esc(item.validation_action || '待补充')}}</dd></div><div class="analysis-item"><dt>分析置信度</dt><dd>${{number(item.analysis_confidence).toFixed(2)}}</dd></div></dl><details class="disclosure"><summary>涉及产品 <span class="summary-count">${{apps.length}} 个</span></summary><div class="details-body">${{appMarkup}}</div></details><details class="disclosure"><summary>原始证据 <span class="summary-count">${{evidence.length}} 条</span></summary><div class="details-body">${{evidenceMarkup}}</div></details></article>`;
  }}).join('') : '<div class="empty">没有可展示的机会。先运行 run 生成分析。</div>';
}}
document.querySelector('#search').addEventListener('input', render);
document.querySelector('#decision').addEventListener('change', render);
document.querySelector('#reset').addEventListener('click', () => {{ document.querySelector('#search').value = ''; document.querySelector('#decision').value = ''; render(); document.querySelector('#search').focus(); }});
render();
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
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError as exc:
        raise ValueError("Dashboard host must be a loopback IP address.") from exc
    if not is_loopback:
        raise ValueError("Dashboard only allows loopback host addresses.")

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
