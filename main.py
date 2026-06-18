import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from src.agent import EmailAgent

APPROVED_EMAILS_DIR = Path(__file__).parent / "approved_emails"
APPROVED_EMAILS_DIR.mkdir(exist_ok=True)

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)

# Singleton: khởi tạo một lần khi container start — đọc Excel và load prompt templates
# một lần duy nhất, tất cả requests sau đó dùng lại mà không cần I/O thêm.
_agent = EmailAgent()

_CAMPAIGN_FIELDS = [
    ("campaign_name", "Campaign Name", "VD: World Cup 2026"),
    ("timeline",      "Timeline",      "VD: 01/07 – 31/07/2026"),
    ("scheme",        "Ưu đãi (Scheme)", "VD: Giảm 20.000đ cho đơn từ 99.000đ"),
    ("sponsor",       "Bên tài trợ (Sponsor)", "VD: Zalopay tài trợ 100%"),
    ("channel",       "Kênh (Channel)", "VD: Online / App"),
    ("cta",           "CTA",           "VD: Xác nhận trước 20/06/2026"),
]

_UI_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Merchant Campaign Email Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fa; color: #1a1a2e; min-height: 100vh; padding: 24px; }
  .container { max-width: 860px; margin: 0 auto; }
  h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; color: #0f3460; }
  .subtitle { font-size: 0.85rem; color: #666; margin-bottom: 24px; }
  .card { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; }
  label { display: block; font-size: 0.82rem; font-weight: 600; color: #444; margin-bottom: 6px; }
  input, textarea, select { width: 100%; border: 1.5px solid #dde1e7; border-radius: 8px; padding: 10px 14px; font-size: 0.95rem; outline: none; transition: border-color .2s; background: #fff; }
  input:focus, textarea:focus { border-color: #0057b8; }
  textarea { resize: vertical; min-height: 72px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media(max-width:600px) { .grid2 { grid-template-columns: 1fr; } }
  .btn-primary { background: #0057b8; color: #fff; border: none; border-radius: 8px; padding: 11px 28px; font-size: 0.95rem; font-weight: 600; cursor: pointer; transition: background .2s; }
  .btn-primary:hover { background: #0041a8; }
  .btn-primary:disabled { background: #aaa; cursor: not-allowed; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; margin-right: 8px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .badge { display: inline-block; border-radius: 20px; padding: 2px 10px; font-size: 0.78rem; font-weight: 700; }
  .badge-pass { background: #e6f9f0; color: #1a7f45; }
  .badge-fail { background: #fef0f0; color: #c0392b; }
  .badge-skip { background: #fff8e6; color: #a05c00; }
  .badge-cross { background: #eef2ff; color: #3730a3; }
  .result-card { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .section-title { font-size: 0.78rem; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 8px; }
  .email-subject { font-size: 1.05rem; font-weight: 700; color: #0f3460; margin-bottom: 12px; padding: 12px 16px; background: #f0f4ff; border-radius: 8px; border-left: 4px solid #0057b8; }
  .email-body { white-space: pre-wrap; font-size: 0.92rem; line-height: 1.7; color: #333; background: #fafbfc; border-radius: 8px; padding: 16px; border: 1px solid #eee; max-height: 420px; overflow-y: auto; }
  .meta-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
  .meta-item { font-size: 0.83rem; color: #555; }
  .meta-item strong { color: #222; }
  .strength-list li, .weak-list li { font-size: 0.83rem; padding: 3px 0; color: #444; }
  .strength-list li::before { content: "✓ "; color: #1a7f45; font-weight: 700; }
  .weak-list li::before { content: "△ "; color: #c0392b; font-weight: 700; }
  .error-box { background: #fef0f0; border: 1px solid #f5c6c6; border-radius: 8px; padding: 14px; color: #c0392b; font-size: 0.9rem; }
  details.campaign-section { border: 1.5px dashed #c7d2e7; border-radius: 10px; padding: 0; margin-top: 16px; }
  details.campaign-section[open] { border-color: #0057b8; }
  details.campaign-section summary { padding: 12px 16px; cursor: pointer; font-size: 0.85rem; font-weight: 600; color: #0057b8; list-style: none; display: flex; align-items: center; gap: 8px; }
  details.campaign-section summary::before { content: "▶"; font-size: 0.7rem; transition: transform .2s; }
  details.campaign-section[open] summary::before { transform: rotate(90deg); }
  details.campaign-section .campaign-body { padding: 0 16px 16px; }
  .hint { font-size: 0.78rem; color: #888; margin-top: 4px; }
  .toggle-row { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
  .toggle-row input[type=checkbox] { width: auto; accent-color: #0057b8; width: 16px; height: 16px; }
  .toggle-label { font-size: 0.85rem; color: #444; }
  .mode-hint { font-size: 0.78rem; color: #888; }
  details.result-details { margin-top: 12px; }
  details.result-details summary { cursor: pointer; font-size: 0.82rem; color: #0057b8; font-weight: 600; }
  .copy-btn { background: none; border: 1.5px solid #dde1e7; color: #555; padding: 5px 12px; font-size: 0.78rem; border-radius: 6px; cursor: pointer; float: right; margin-top: -4px; }
  .copy-btn:hover { background: #f0f4ff; border-color: #0057b8; color: #0057b8; }
  #status-bar { font-size: 0.83rem; color: #888; min-height: 20px; }
</style>
</head>
<body>
<div class="container">
  <h1>Merchant Campaign Email Agent</h1>
  <p class="subtitle">Zalopay · Claw-a-thon 2026 · Sinh email CTKM tự động</p>

  <div class="card">
    <!-- Merchant + instruction -->
    <label for="merchant">Tên Merchant *</label>
    <input id="merchant" type="text" list="merchant-list" placeholder="VD: KFC, BreadTalk, Starbucks..." autocomplete="off" />
    <datalist id="merchant-list"></datalist>
    <p class="hint" id="merchant-hint">Nhập tên merchant có trong file dữ liệu, hoặc bất kỳ merchant mới nào (điền thông tin campaign bên dưới).</p>

    <div style="margin-top:14px;">
      <label for="instruction">Ghi chú / Yêu cầu thêm (tuỳ chọn)</label>
      <textarea id="instruction" placeholder="VD: Viết ngắn gọn, không quá 150 từ..."></textarea>
    </div>

    <!-- Campaign info (manual input for unknown merchants) -->
    <details class="campaign-section" id="campaign-section">
      <summary>Thông tin Campaign (điền nếu merchant chưa có trong file)</summary>
      <div class="campaign-body">
        <p class="hint" style="margin-bottom:12px;">Nếu merchant không có trong file dữ liệu, hệ thống sẽ dùng thông tin bạn nhập ở đây. Để trống các trường nếu merchant đã có sẵn.</p>
        <div class="grid2">
          <div>
            <label>Campaign Name</label>
            <input id="f_campaign_name" type="text" placeholder="VD: World Cup 2026" />
          </div>
          <div>
            <label>Timeline</label>
            <input id="f_timeline" type="text" placeholder="VD: 01/07 – 31/07/2026" />
          </div>
          <div>
            <label>Ưu đãi (Scheme)</label>
            <input id="f_scheme" type="text" placeholder="VD: Giảm 20.000đ cho đơn từ 99.000đ" />
          </div>
          <div>
            <label>Bên tài trợ (Sponsor)</label>
            <input id="f_sponsor" type="text" placeholder="VD: Zalopay tài trợ 100%" />
          </div>
          <div>
            <label>Kênh (Channel)</label>
            <input id="f_channel" type="text" placeholder="VD: Online / App" />
          </div>
          <div>
            <label>CTA</label>
            <input id="f_cta" type="text" placeholder="VD: Xác nhận trước 20/06/2026" />
          </div>
        </div>
      </div>
    </details>

    <!-- Mode toggle + submit -->
    <div class="toggle-row">
      <input type="checkbox" id="quick-mode" />
      <span class="toggle-label">Chế độ nhanh</span>
      <span class="mode-hint">(bỏ qua review tự động — nhanh hơn ~50%, không có QA score)</span>
    </div>

    <div style="margin-top:16px; display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
      <button class="btn-primary" id="btn" onclick="generate()">Tạo Email</button>
      <div id="status-bar"></div>
    </div>
  </div>

  <div id="result"></div>
</div>

<script>
let _currentMerchant = '';

// Load merchant list for autocomplete
(async () => {
  try {
    const r = await fetch('/merchants');
    const data = await r.json();
    const dl = document.getElementById('merchant-list');
    (data.merchants || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      dl.appendChild(opt);
    });
  } catch (_) {}
})();

function getCampaignInfo() {
  const fields = {
    'Campaign Name': document.getElementById('f_campaign_name').value.trim(),
    'Timeline':      document.getElementById('f_timeline').value.trim(),
    'Scheme':        document.getElementById('f_scheme').value.trim(),
    'Sponsor':       document.getElementById('f_sponsor').value.trim(),
    'Channel':       document.getElementById('f_channel').value.trim(),
    'CTA':           document.getElementById('f_cta').value.trim(),
  };
  const hasAny = Object.values(fields).some(v => v);
  return hasAny ? fields : null;
}

async function generate() {
  const merchant = document.getElementById('merchant').value.trim();
  if (!merchant) { alert('Vui lòng nhập tên Merchant.'); return; }

  const btn = document.getElementById('btn');
  const statusBar = document.getElementById('status-bar');
  const resultDiv = document.getElementById('result');
  const skipReview = document.getElementById('quick-mode').checked;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Đang tạo email...';
  statusBar.textContent = skipReview ? 'Chế độ nhanh: sinh email...' : 'Sinh email + review tự động...';
  resultDiv.innerHTML = '';

  const payload = { merchant_name: merchant, skip_review: skipReview };
  const instruction = document.getElementById('instruction').value.trim();
  if (instruction) payload.user_instruction = instruction;
  const ci = getCampaignInfo();
  if (ci) payload.campaign_info = ci;

  try {
    const resp = await fetch('/invocations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    _currentMerchant = data.merchant || merchant;
    if (data.error && data.error.includes('not found') && !ci) {
      document.getElementById('campaign-section').open = true;
      document.getElementById('f_campaign_name').focus();
    }
    renderResult(data);
    statusBar.textContent = '';
  } catch (e) {
    resultDiv.innerHTML = '<div class="error-box">Lỗi kết nối: ' + e.message + '</div>';
    statusBar.textContent = '';
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Tạo Email';
  }
}

function copyText(id) {
  const el = document.getElementById(id);
  navigator.clipboard.writeText(el.innerText).then(() => {
    const btn = el.previousElementSibling;
    btn.textContent = '✓ Đã copy';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  });
}

function renderResult(d) {
  if (d.error) {
    const extra = d.error.includes('not found')
      ? '<br><small style="color:#555">👆 Hãy điền thông tin Campaign bên trên để tiếp tục.</small>'
      : '';
    document.getElementById('result').innerHTML =
      '<div class="error-box" style="margin-top:0"><strong>Lỗi:</strong> ' + escHtml(d.error) + extra + '</div>';
    return;
  }
  const review = d.review || {};
  const skipped = review.skipped;
  const passed = review.passed;
  const score = review.score;
  const strengths = (review.strengths || []).slice(0, 5);
  const weaknesses = (review.weaknesses || []);
  const suggestions = (review.improvement_suggestions || []);
  const history = (d.generation_history || []);
  const crossMerchant = d.approved_files && d.approved_files.length > 0 &&
    !d.approved_files.some(f => f.toLowerCase().includes(d.merchant.toLowerCase()));

  const scoreBadge = skipped
    ? '<span class="badge badge-skip">Chế độ nhanh</span>'
    : (passed
        ? '<span class="badge badge-pass">Passed ' + score + '/5</span>'
        : '<span class="badge badge-fail">Score ' + score + '/5</span>');

  const strengthsHtml = strengths.length
    ? '<ul class="strength-list">' + strengths.map(s => '<li>' + escHtml(s) + '</li>').join('') + '</ul>'
    : '<p style="color:#888;font-size:.83rem">—</p>';
  const weakHtml = (weaknesses.length || suggestions.length)
    ? '<ul class="weak-list">' +
        weaknesses.map(w => '<li>' + escHtml(w) + '</li>').join('') +
        suggestions.map(s => '<li>' + escHtml(s) + '</li>').join('') +
      '</ul>'
    : '<p style="color:#888;font-size:.83rem">—</p>';
  const historyHtml = history.map(h =>
    '<div style="font-size:.82rem;color:#555;padding:2px 0">Lần ' + h.attempt + ': ' +
    (h.score != null ? h.score + '/5' : '—') + ' — ' + escHtml(h.reason) + '</div>'
  ).join('');

  document.getElementById('result').innerHTML = `
    <div class="result-card">
      <div class="meta-row">
        <div class="meta-item"><strong>Merchant:</strong> ${escHtml(d.merchant)}</div>
        <div class="meta-item"><strong>Campaign:</strong> ${escHtml(d.campaign || '—')}</div>
        <div class="meta-item">${scoreBadge}</div>
        <div class="meta-item"><strong>Attempts:</strong> ${d.attempts}</div>
        <div class="meta-item"><strong>Samples:</strong> ${d.approved_samples_used}
          ${crossMerchant ? '<span class="badge badge-cross" title="Tham khảo từ merchant khác">cross-merchant</span>' : ''}
        </div>
      </div>

      <div class="section-title">Tiêu đề <span style="font-weight:400;color:#aaa;font-size:.75rem">(có thể chỉnh sửa)</span></div>
      <input type="text" id="edit-subject" value="${escAttr(d.subject)}" style="font-size:1rem;font-weight:600;color:#0f3460;border-color:#c7d2e7;margin-bottom:12px;" />

      <div class="section-title" style="margin-top:4px;">
        Nội dung email <span style="font-weight:400;color:#aaa;font-size:.75rem">(có thể chỉnh sửa)</span>
        <button class="copy-btn" id="copy-body-btn" onclick="copyEditBody()">Copy</button>
      </div>
      <textarea id="edit-body" style="min-height:260px;font-size:0.92rem;line-height:1.7;color:#333;background:#fafbfc;border-color:#c7d2e7;">${escHtml(d.body)}</textarea>

      <div style="margin-top:14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
        <button class="btn-primary" onclick="approveEmail()">Approve &amp; Save</button>
        <div id="approve-status" style="font-size:0.85rem;color:#1a7f45;"></div>
      </div>
      <p style="font-size:0.76rem;color:#999;margin-top:8px;">
        Email được approve sẽ được lưu làm mẫu tham khảo cho các lần sinh email sau của cùng merchant.
      </p>

      ${!skipped ? `<details class="result-details" style="margin-top:14px;">
        <summary>Điểm mạnh / Gợi ý cải thiện</summary>
        <div style="margin-top:10px;display:flex;gap:24px;flex-wrap:wrap;">
          <div style="flex:1;min-width:200px;"><div class="section-title">Điểm mạnh</div>${strengthsHtml}</div>
          <div style="flex:1;min-width:200px;"><div class="section-title">Gợi ý</div>${weakHtml}</div>
        </div>
      </details>` : ''}

      ${history.length > 1 ? `<details class="result-details">
        <summary>Lịch sử sinh email (${history.length} lần)</summary>
        <div style="margin-top:8px;">${historyHtml}</div>
      </details>` : ''}
    </div>`;
}

function escHtml(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function copyEditBody() {
  const ta = document.getElementById('edit-body');
  if (!ta) return;
  navigator.clipboard.writeText(ta.value).then(() => {
    const btn = document.getElementById('copy-body-btn');
    btn.textContent = '✓ Đã copy';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  });
}

async function approveEmail() {
  const subject = (document.getElementById('edit-subject')?.value || '').trim();
  const body    = (document.getElementById('edit-body')?.value || '').trim();
  const merchant = _currentMerchant;
  const statusEl = document.getElementById('approve-status');

  if (!subject || !body) { alert('Subject và body không được để trống.'); return; }
  if (!merchant) { alert('Không xác định được merchant.'); return; }

  statusEl.textContent = 'Đang lưu...';
  statusEl.style.color = '#888';

  try {
    const resp = await fetch('/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, subject, body })
    });
    const data = await resp.json();
    if (data.error) {
      statusEl.textContent = 'Lỗi: ' + data.error;
      statusEl.style.color = '#c0392b';
    } else {
      statusEl.innerHTML = '✓ Đã lưu: <code>' + escHtml(data.saved) + '</code> — email này sẽ được dùng làm mẫu tham khảo cho lần sau.';
      statusEl.style.color = '#1a7f45';
    }
  } catch (e) {
    statusEl.textContent = 'Lỗi kết nối: ' + e.message;
    statusEl.style.color = '#c0392b';
  }
}

document.getElementById('merchant').addEventListener('keydown', e => {
  if (e.key === 'Enter') generate();
});
</script>
</body>
</html>"""

async def _ui_handler(request: Request) -> HTMLResponse:
    return HTMLResponse(_UI_HTML)

async def _approve_handler(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    merchant = (data.get("merchant") or "").strip()
    subject  = (data.get("subject") or "").strip()
    body     = (data.get("body") or "").strip()

    if not merchant or not subject or not body:
        return JSONResponse({"error": "merchant, subject, and body are required"}, status_code=400)

    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name    = merchant.lower().replace(" ", "_")
    filename     = f"{safe_name}_{timestamp}.txt"
    filepath     = APPROVED_EMAILS_DIR / filename
    filepath.write_text(f"Subject: {subject}\n\n---\n\n{body}", encoding="utf-8")

    return JSONResponse({"saved": filename})

async def _merchants_handler(request: Request) -> JSONResponse:
    try:
        merchants = _agent.reader.list_merchants()
    except Exception:
        merchants = []
    return JSONResponse({"merchants": merchants})

app = GreenNodeAgentBaseApp()
app.add_route("/", _ui_handler, methods=["GET"])
app.add_route("/approve", _approve_handler, methods=["POST"])
app.add_route("/merchants", _merchants_handler, methods=["GET"])


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Main agent entrypoint for POST /invocations.

    Expected payload:
        {
            "merchant_name": "KFC",
            "user_instruction": "Optional instruction text"
        }
    """
    merchant_name = payload.get("merchant_name") or payload.get("merchant")
    if not merchant_name or not isinstance(merchant_name, str) or not merchant_name.strip():
        return {
            "error": "Missing required field 'merchant_name' in request payload."
        }

    user_instruction = payload.get("user_instruction", "") or ""
    if not isinstance(user_instruction, str):
        user_instruction = str(user_instruction)

    campaign_info = payload.get("campaign_info") or None
    if isinstance(campaign_info, dict) and not any(campaign_info.values()):
        campaign_info = None

    skip_review = bool(payload.get("skip_review", False))

    result = _agent.run(
        merchant_name.strip(),
        user_instruction.strip(),
        campaign_info=campaign_info,
        skip_review=skip_review,
    )
    return result


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
