"""
EDM Conversation Status Dashboard

Usage: python edm_dashboard.py [--port 8765] [--json-file edmmailanalyzer.json]
"""
import argparse
import http.server
import json
import re
import webbrowser

STEP_LABELS = {
    1: "EDM请求发起",
    2: "测试已发送等待确认审批",
    3: "Peer reviewed, 等待Nanbo审批",
    4: "审批完成",
    5: "审批结果告知PS",
    6: "Formal EDM已发送",
    7: "确认收到最终结束",
}


def load_data(path):
    for enc in ["utf-8-sig", "utf-8", "gbk"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return []


def build_conversations(raw):
    # Only keep emails whose subject contains '[EDM test and distribution]'
    raw = [r for r in raw if '[EDM test and distribution]' in r.get("subject", "")]

    # First pass: group all emails by conversation_id
    convs = {}
    for r in raw:
        cid = r["conversation_id"]
        if cid not in convs:
            convs[cid] = []
        convs[cid].append(r)

    # Filter out conversations that have emails from 21V-WAPHYNET
    noisy = {"21v-waphynet@oe.21vianet.com"}
    convs = {
        cid: emails for cid, emails in convs.items()
        if not any(e["sender"].lower() in noisy for e in emails)
    }

    result = []
    for cid, emails in convs.items():
        emails.sort(key=lambda x: x.get("conversation_step", 0))
        subject = emails[0]["subject"]
        sn_match = re.search(r"SN-(\d+)", subject)
        inc_match = re.search(r"Incident\s+(\d+)", subject)

        # Cap steps at 7: emails beyond step 7 all map to step 7
        capped_emails = []
        for e in emails:
            rec = dict(e)
            rec["conversation_step"] = min(e.get("conversation_step", 1), 7)
            capped_emails.append(rec)
        # Deduplicate: if multiple emails map to step 7, keep the latest
        seen_steps = {}
        ordered = []
        for e in capped_emails:
            s = e["conversation_step"]
            if s in seen_steps:
                seen_steps[s] = e  # keep latest
            else:
                seen_steps[s] = e
                ordered.append(e)

        result.append({
            "conversation_id": cid,
            "sn": sn_match.group(0) if sn_match else "",
            "incident": inc_match.group(1) if inc_match else "",
            "subject": subject,
            "total_steps": len(ordered),
            "current_step": len(ordered),
            "emails": ordered,
        })

    result.sort(key=lambda x: x["emails"][0]["date"])
    return result


def make_html(data_json):
    step_labels_js = json.dumps(STEP_LABELS, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDM 邮件状态看板</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background: #f0f2f5; padding: 24px; }}
  h1 {{ text-align: center; margin-bottom: 6px; color: #1a1a2e; }}
  .subtitle {{ text-align: center; color: #666; margin-bottom: 24px; font-size: 13px; }}
  .summary {{ display: flex; justify-content: center; gap: 32px; margin-bottom: 24px; }}
  .summary .card {{ background: #fff; padding: 16px 32px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1); text-align: center; }}
  .summary .card .num {{ font-size: 28px; font-weight: bold; }}
  .summary .card .label {{ font-size: 13px; color: #888; margin-top: 4px; }}
  .conv-card {{ background: #fff; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1); overflow: hidden; }}
  .conv-header {{ padding: 16px 20px; cursor: pointer; display: flex; align-items: center; gap: 16px; user-select: none; }}
  .conv-header:hover {{ background: #f5f7fa; }}
  .conv-header .toggle {{ font-size: 12px; color: #999; transition: transform .2s; min-width: 16px; }}
  .conv-header .toggle.open {{ transform: rotate(90deg); }}
  .conv-header .info {{ flex: 1; }}
  .conv-header .subject {{ font-size: 14px; color: #333; font-weight: 500; }}
  .conv-header .meta {{ font-size: 12px; color: #999; margin-top: 4px; }}
  .badge {{ font-size: 12px; padding: 3px 10px; border-radius: 10px; color: #fff; white-space: nowrap; font-weight: 500; }}
  .badge.done {{ background: #52c41a; }}
  .badge.progress {{ background: #faad14; }}
  .progress-bar {{ display: flex; padding: 0 20px 10px; gap: 2px; }}
  .progress-bar .seg {{ flex: 1; height: 4px; border-radius: 2px; background: #e8e8e8; }}
  .progress-bar .seg.done {{ background: #52c41a; }}
  .progress-bar .seg.current {{ background: #faad14; }}
  .conv-detail {{ display: none; border-top: 1px solid #f0f0f0; padding: 16px 20px; }}
  .conv-detail.open {{ display: block; }}
  .step-row {{ display: flex; align-items: flex-start; gap: 12px; padding: 10px 0; position: relative; }}
  .step-row:not(:last-child)::after {{
    content: ''; position: absolute; left: 15px; top: 36px; bottom: -10px; width: 2px; background: #e8e8e8;
  }}
  .step-row.done:not(:last-child)::after {{ background: #52c41a; }}
  .step-dot {{ width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: bold; color: #fff; flex-shrink: 0; }}
  .step-dot.done {{ background: #52c41a; }}
  .step-dot.current {{ background: #faad14; }}
  .step-dot.pending {{ background: #d9d9d9; color: #999; }}
  .step-content {{ flex: 1; }}
  .step-label {{ font-size: 14px; font-weight: 500; color: #333; }}
  .step-info {{ font-size: 12px; color: #888; margin-top: 2px; }}
  .step-info .sender {{ color: #1890ff; }}
  .num-green {{ color: #52c41a; }}
  .num-yellow {{ color: #faad14; }}
  .num-blue {{ color: #1890ff; }}
  .summary .card {{ cursor: pointer; transition: box-shadow .2s; }}
  .summary .card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,.18); }}
  .summary .card.active {{ box-shadow: 0 0 0 2px #1890ff; }}
  .filter-active {{ font-size: 13px; color: #1890ff; text-align: center; margin-bottom: 12px; }}
  .filter-active span {{ cursor: pointer; text-decoration: underline; }}
</style>
</head>
<body>
<h1>EDM 邮件状态看板</h1>
<p class="subtitle">数据来源: edmmailanalyzer.json</p>
<div class="summary" id="summary"></div>
<div id="container"></div>

<script>
var convData = {data_json};
var STEP_LABELS = {step_labels_js};
var filterMode = 'all';

function render(fMode) {{
  filterMode = fMode || 'all';
  var totalConvs = convData.length;
  var completed = 0;
  for (var i = 0; i < convData.length; i++) {{
    convData[i]._isComplete = convData[i].emails.length >= 7;
    if (convData[i]._isComplete) completed++;
  }}
  var inProgress = totalConvs - completed;

  // Summary cards — use createElement to avoid quote escaping issues
  var summaryEl = document.getElementById('summary');
  summaryEl.innerHTML = '';
  var cardData = [
    {{ label: '总对话数', num: totalConvs, color: 'num-blue', mode: 'all' }},
    {{ label: '进行中', num: inProgress, color: 'num-yellow', mode: 'progress' }},
    {{ label: '已完成', num: completed, color: 'num-green', mode: 'done' }},
  ];
  cardData.forEach(function(cd) {{
    var card = document.createElement('div');
    card.className = 'card';
    card.onclick = function() {{ render(cd.mode); }};
    card.innerHTML = '<div class="num ' + cd.color + '">' + cd.num + '</div><div class="label">' + cd.label + '</div>';
    summaryEl.appendChild(card);
  }});

  // Highlight active card
  var cards = summaryEl.querySelectorAll('.card');
  for (var ci = 0; ci < cards.length; ci++) {{
    cards[ci].classList.toggle('active', (filterMode === cardData[ci].mode));
  }}

  // Filter
  var filtered = convData;
  if (filterMode === 'progress') filtered = convData.filter(function(c) {{ return !c._isComplete; }});
  if (filterMode === 'done') filtered = convData.filter(function(c) {{ return c._isComplete; }});

  var container = document.getElementById('container');
  container.innerHTML = '';

  if (filterMode !== 'all') {{
    var hint = document.createElement('div');
    hint.className = 'filter-active';
    var label = filterMode === 'progress' ? '进行中' : '已完成';
    hint.innerHTML = '当前筛选: <strong>' + label + '</strong>（' + filtered.length + ' 个对话）— ';
    var clearLink = document.createElement('span');
    clearLink.style.cssText = 'cursor:pointer;text-decoration:underline';
    clearLink.textContent = '显示全部';
    clearLink.onclick = function() {{ render('all'); }};
    hint.appendChild(clearLink);
    container.appendChild(hint);
  }}

  // Render each card by index
  for (var fi = 0; fi < filtered.length; fi++) {{
    var conv = filtered[fi];
    var cardId = 'c' + fi;

    var card = document.createElement('div');
    card.className = 'conv-card';

    // Header
    var header = document.createElement('div');
    header.className = 'conv-header';
    var dateStr = conv.emails[0].date.substring(0, 10);
    var snTag = conv.sn ? '<strong>' + conv.sn + '</strong> — ' : '';
    var subjShort = conv.subject.substring(0, 90) + (conv.subject.length > 90 ? '...' : '');
    var isComplete = conv._isComplete;

    header.innerHTML =
      '<span class="toggle" id="t-' + cardId + '">▶</span>' +
      '<div class="info">' +
        '<div class="subject">' + snTag + subjShort + '</div>' +
        '<div class="meta">' + dateStr + ' · ' + conv.emails.length + ' 封邮件</div>' +
      '</div>' +
      '<span class="badge ' + (isComplete ? 'done' : 'progress') + '">' +
        (isComplete ? '已完成' : '进行中 Step ' + conv.emails.length) +
      '</span>';

    // Progress bar
    var bar = document.createElement('div');
    bar.className = 'progress-bar';
    for (var s = 1; s <= 7; s++) {{
      var seg = document.createElement('div');
      seg.className = 'seg';
      if (isComplete || s < conv.emails.length) {{
        seg.classList.add('done');
      }} else if (s === conv.emails.length) {{
        seg.classList.add('current');
      }}
      bar.appendChild(seg);
    }}

    // Detail
    var detail = document.createElement('div');
    detail.className = 'conv-detail';
    detail.id = 'd-' + cardId;

    for (var s = 1; s <= 7; s++) {{
      var email = null;
      for (var e = 0; e < conv.emails.length; e++) {{
        if (conv.emails[e].conversation_step === s) {{ email = conv.emails[e]; break; }}
      }}
      var row = document.createElement('div');
      var isD, isC, isP;
      if (isComplete) {{
        isD = true;
        isC = isP = false;
      }} else {{
        isD = s < conv.emails.length;
        isC = s === conv.emails.length;
        isP = s > conv.emails.length;
      }}
      row.className = 'step-row' + (isD ? ' done' : '');

      var dotClass = 'step-dot';
      if (isD) dotClass += ' done';
      else if (isC) dotClass += ' current';
      else dotClass += ' pending';

      var dotText = isD ? '✓' : s;
      var infoHTML;
      if (email) {{
        infoHTML = '<span class="sender">' + email.sender.split('@')[0] + '</span> · ' + email.date.substring(0, 16);
      }} else {{
        infoHTML = '<span style="color:#ccc">尚未到达</span>';
      }}

      row.innerHTML =
        '<div class="' + dotClass + '">' + dotText + '</div>' +
        '<div class="step-content">' +
          '<div class="step-label">' + STEP_LABELS[s] + '</div>' +
          '<div class="step-info">' + infoHTML + '</div>' +
        '</div>';
      detail.appendChild(row);
    }}

    card.appendChild(header);
    card.appendChild(bar);
    card.appendChild(detail);
    container.appendChild(card);

    // Toggle click — use data attribute, no getElementById
    header.setAttribute('data-card', cardId);
    header.addEventListener('click', (function(cid) {{
      return function() {{
        var t = document.getElementById('t-' + cid);
        var d = document.getElementById('d-' + cid);
        if (t) t.classList.toggle('open');
        if (d) d.classList.toggle('open');
      }};
    }})(cardId));
  }}
}}

render('all');
</script>
</body>
</html>"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    html_page = None

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.html_page.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="EDM Dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--json-file", default="edmmailanalyzer.json")
    args = parser.parse_args()

    raw = load_data(args.json_file)
    if not raw:
        print("No data found.")
        return

    convs = build_conversations(raw)
    data_json = json.dumps(convs, ensure_ascii=False)
    html = make_html(data_json)

    DashboardHandler.html_page = html
    server = http.server.HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{args.port}")

    try:
        webbrowser.open(f"http://localhost:{args.port}")
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
