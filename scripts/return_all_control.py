from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, url_for

from set_return_all import STATE_PATH, read_state, set_return_all

ROOT = Path(__file__).resolve().parents[1]
PAGE_TITLE = "Return All Control"

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ page_title }}</title>
    <style>
      body {
        margin: 0;
        font-family: "Segoe UI", Arial, sans-serif;
        background: #12090b;
        color: #f8e9ea;
      }
      .wrap {
        max-width: 760px;
        margin: 0 auto;
        padding: 28px 20px 40px;
      }
      .panel {
        background: #241113;
        border: 1px solid #5a1b22;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
      }
      .state {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px;
        margin-top: 18px;
      }
      .state-card {
        background: #180d0f;
        border: 1px solid #412126;
        border-radius: 14px;
        padding: 14px;
      }
      .label {
        font-size: 12px;
        color: #d9b4b8;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
      .value {
        margin-top: 6px;
        font-size: 18px;
        font-weight: 600;
        word-break: break-word;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin: 22px 0;
      }
      button {
        border: 0;
        border-radius: 16px;
        cursor: pointer;
        font-weight: 700;
      }
      .enable {
        min-height: 108px;
        flex: 1 1 360px;
        font-size: 28px;
        background: linear-gradient(180deg, #d12f38, #8d1117);
        color: #fff5f6;
      }
      .disable {
        min-height: 56px;
        flex: 1 1 220px;
        font-size: 18px;
        background: #204e28;
        color: #e8fff0;
      }
      .meta {
        margin-top: 18px;
        color: #d8c5c7;
        font-size: 14px;
      }
      input[type="text"] {
        width: 100%;
        box-sizing: border-box;
        margin-top: 8px;
        border-radius: 12px;
        border: 1px solid #5c3136;
        padding: 10px 12px;
        background: #130a0c;
        color: #fff4f5;
      }
      label {
        display: block;
        margin-top: 14px;
        font-size: 14px;
        color: #f2d4d7;
      }
      .checkbox {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 14px;
      }
      .notice {
        margin-top: 18px;
        padding: 12px 14px;
        border-radius: 12px;
        background: #1b0f11;
        border: 1px solid #4d2329;
      }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        background: #130a0c;
        border: 1px solid #412126;
        border-radius: 12px;
        padding: 14px;
        color: #ffdce0;
      }
      .active {
        color: #ffb4ba;
      }
      .inactive {
        color: #a8efb7;
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="panel">
        <h1>{{ page_title }}</h1>
        <p>Single-purpose governance control for the spine.</p>
        <div class="actions">
          <form method="post" action="{{ url_for('enable') }}" style="flex: 1 1 360px;">
            <label for="enable-issued-by">Issued by</label>
            <input id="enable-issued-by" type="text" name="issued_by" value="{{ state.issued_by or 'operator' }}">
            <label for="enable-reason">Reason</label>
            <input id="enable-reason" type="text" name="reason" value="{{ state.reason }}">
            <label class="checkbox">
              <input type="checkbox" name="allow_custodial_bypass" {% if state.allow_custodial_bypass %}checked{% endif %}>
              Allow custodial rapid self-heal / repair bypass
            </label>
            <div style="margin-top: 14px;">
              <button class="enable" type="submit">Return All to Base</button>
            </div>
          </form>
          <form method="post" action="{{ url_for('disable') }}" style="flex: 1 1 220px;">
            <label for="disable-issued-by">Issued by</label>
            <input id="disable-issued-by" type="text" name="issued_by" value="{{ state.issued_by or 'operator' }}">
            <label for="disable-reason">Clear reason</label>
            <input id="disable-reason" type="text" name="reason" value="">
            <div style="margin-top: 14px;">
              <button class="disable" type="submit">Clear Return All</button>
            </div>
          </form>
        </div>
        <div class="state">
          <div class="state-card">
            <div class="label">Enabled</div>
            <div class="value {% if state.enabled %}active{% else %}inactive{% endif %}">{{ state.enabled }}</div>
          </div>
          <div class="state-card">
            <div class="label">Issued By</div>
            <div class="value">{{ state.issued_by or '—' }}</div>
          </div>
          <div class="state-card">
            <div class="label">Issued At</div>
            <div class="value">{{ state.issued_at or '—' }}</div>
          </div>
          <div class="state-card">
            <div class="label">Allow Custodial Bypass</div>
            <div class="value">{{ state.allow_custodial_bypass }}</div>
          </div>
        </div>
        <div class="notice">
          <strong>Reason:</strong> {{ state.reason or '—' }}
        </div>
        <div class="meta">
          <div>State file: {{ state_path }}</div>
        </div>
        <div class="meta">
          <pre>{{ state_json }}</pre>
        </div>
      </div>
    </div>
  </body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        state = read_state()
        return render_template_string(
            PAGE_TEMPLATE,
            page_title=PAGE_TITLE,
            state=state,
            state_path=str(STATE_PATH),
            state_json=json.dumps(state, indent=2),
            html=html,
        )

    @app.post("/enable")
    def enable():
        set_return_all(
            enabled=True,
            issued_by=request.form.get("issued_by", "operator").strip() or "operator",
            reason=request.form.get("reason", "").strip(),
            allow_custodial_bypass=bool(request.form.get("allow_custodial_bypass")),
        )
        return redirect(url_for("index"))

    @app.post("/disable")
    def disable():
        set_return_all(
            enabled=False,
            issued_by=request.form.get("issued_by", "operator").strip() or "operator",
            reason=request.form.get("reason", "").strip(),
            allow_custodial_bypass=False,
        )
        return redirect(url_for("index"))

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a tiny local Return All control page.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5052)
    args = parser.parse_args()
    app = create_app()
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
