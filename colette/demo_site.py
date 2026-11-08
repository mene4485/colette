"""Local mock-up of the Free Mobile customer area, with a fictitious account, for the Colette demo.

Served on http://localhost:8000 (standard library only). Possible tasks:
- change plan (list of plans → summary → "Confirm plan change");
- download the most recent bill (real PDF generated on the fly);
- edit contact details (address, email, contact phone → "Save changes").

Demo account: ID 12345678, password colette (shown nowhere on the site).
Changes are kept in demo_data/account.json; /reset resets the account.
This is NOT the Free website: a "demo mock-up" banner is shown on every page.
"""

from __future__ import annotations

import calendar
import copy
import datetime as dt
import hashlib
import hmac
import html
import json
import re
import secrets
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "demo_data" / "account.json"
DEFAULT_PORT = 8000

DEMO_LOGIN = "12345678"
DEMO_PASSWORD = "colette"

PLANS = {
    "2e": {"name": "€2 Plan", "price": 2.00,
           "details": "2 hours of calls · Unlimited texts and MMS · 50 MB of data"},
    "serie": {"name": "Free Series 120 GB", "price": 9.99,
              "details": "Unlimited calls, texts and MMS · 120 GB on 4G"},
    "5g": {"name": "Free 5G 300 GB Plan", "price": 19.99,
           "details": "Unlimited calls, texts and MMS · 300 GB on 5G · 35 GB from Europe"},
    "max": {"name": "Free 5G Max 350 GB Plan", "price": 29.99,
            "details": "Unlimited calls, texts and MMS · 350 GB on 5G · 35 GB from 100 destinations"},
}

DEFAULT_ACCOUNT = {
    "holder": "Géraldine Martin",
    "line": "06 12 34 56 78",
    "plan": "5g",
    "pending_plan": None,
    "address": "12 rue des Lilas",
    "postcode": "75020",
    "city": "Paris",
    "email": "geraldine.martin@exemple.fr",
    "contact_phone": "01 43 00 00 00",
    "history": [],
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def euros(x: float) -> str:
    return f"€{x:.2f}"


def first_of_next_month(today: Optional[dt.date] = None) -> dt.date:
    today = today or dt.date.today()
    return (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)


def date_en(d: dt.date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


# ---- account data ----------------------------------------------------------
class Store:
    def __init__(self, path: Path = DATA_PATH) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if "account" in data and "secret" in data:
                return data
        except (OSError, ValueError):
            pass
        return {"account": copy.deepcopy(DEFAULT_ACCOUNT), "secret": secrets.token_hex(16)}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset(self) -> None:
        with self.lock:
            self.data["account"] = copy.deepcopy(DEFAULT_ACCOUNT)
            self.data["secret"] = secrets.token_hex(16)  # logs everyone out
            self.save()

    @property
    def account(self) -> dict:
        return self.data["account"]

    def token(self) -> str:
        return hmac.new(self.data["secret"].encode(), DEMO_LOGIN.encode(), hashlib.sha256).hexdigest()

    def log(self, what: str) -> None:
        self.account["history"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "what": what})


def invoices(account: dict, today: Optional[dt.date] = None) -> list[dict]:
    """The last 6 bills, most recent first (bill for month M issued on the 1st of month M+1)."""
    today = today or dt.date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(6):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        issued = first_of_next_month(dt.date(y, m, 1))
        out.append({
            "id": f"FM{y}{m:02d}{account['line'][-5:].replace(' ', '')}",
            "period": f"{MONTHS[m - 1]} {y}",
            "period_start": dt.date(y, m, 1),
            "period_end": dt.date(y, m, calendar.monthrange(y, m)[1]),
            "issued": issued,
            "amount": PLANS[account["plan"]]["price"],
        })
    return out


# ---- minimal PDF (text only, Helvetica, WinAnsi for accents and €) ------------
def make_pdf(lines: list[tuple[str, int, str]]) -> bytes:
    """lines = [(font "R"|"B", size, text)] top to bottom."""
    def esc(s: str) -> bytes:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252", "replace")

    stream = b"BT 56 780 Td\n"
    for font, size, text in lines:
        stream += f"/F{'2' if font == 'B' else '1'} {size} Tf {size + 8} TL\n".encode()
        stream += b"(" + esc(text) + b") Tj T*\n"
    stream += b"ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def invoice_pdf(account: dict, inv: dict) -> bytes:
    plan = PLANS[account["plan"]]
    ht = inv["amount"] / 1.2
    return make_pdf([
        ("B", 20, "Free Mobile — Bill (demo mock-up)"),
        ("R", 10, "Fictitious document generated for the Colette demo. This is not a real bill."),
        ("R", 11, ""),
        ("B", 13, f"Bill No. {inv['id']}"),
        ("R", 11, f"Period: {date_en(inv['period_start'])} to {date_en(inv['period_end'])}"),
        ("R", 11, f"Issued on: {date_en(inv['issued'])}"),
        ("R", 11, ""),
        ("B", 12, "Account holder"),
        ("R", 11, account["holder"]),
        ("R", 11, account["address"]),
        ("R", 11, f"{account['postcode']} {account['city']}"),
        ("R", 11, f"Line: {account['line']}"),
        ("R", 11, ""),
        ("B", 12, "Details"),
        ("R", 11, f"{plan['name']} — monthly subscription"),
        ("R", 11, f"Amount excl. VAT: {euros(ht)}"),
        ("R", 11, f"VAT 20%: {euros(inv['amount'] - ht)}"),
        ("B", 13, f"Total incl. VAT: {euros(inv['amount'])}"),
        ("R", 11, ""),
        ("R", 10, "Paid automatically by direct debit from your bank account."),
    ])


# ---- HTML -------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#f2f2f2;color:#333;font-size:15px}
a{color:#cd1e25}.demo{background:#f6f6f6;color:#9a9a9a;font-size:11px;text-align:center;padding:3px 8px}
header{background:#cd1e25;color:#fff;display:flex;align-items:center;gap:18px;padding:0 24px;height:64px}
.logo{font-size:34px;font-weight:900;letter-spacing:-1px;text-transform:lowercase}.logo small{font-size:14px;font-weight:400;letter-spacing:0;margin-left:6px}
header .space{font-size:15px;opacity:.95;border-left:1px solid rgba(255,255,255,.5);padding-left:18px}
header .user{margin-left:auto;font-size:13px;text-align:right}header .user a{color:#fff}
.wrap{display:flex;max-width:1180px;margin:0 auto;padding:20px;gap:20px;align-items:flex-start}
nav{width:230px;flex:none;background:#fff;border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,.12)}
nav a{display:block;padding:13px 16px;color:#333;text-decoration:none;border-bottom:1px solid #eee;font-size:14px}
nav a.on{border-left:4px solid #cd1e25;font-weight:bold;background:#fafafa}nav a:hover{background:#f6f6f6}
main{flex:1;min-width:0}h1{font-size:22px;margin:0 0 16px;color:#222}h2{font-size:17px;margin:0 0 12px}
.card{background:#fff;border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,.12);padding:18px 20px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}.grid .card{margin:0}
.muted{color:#777;font-size:13px}.price{font-size:24px;font-weight:bold;color:#cd1e25}
.btn{display:inline-block;background:#cd1e25;color:#fff;border:none;border-radius:3px;padding:10px 18px;font-size:14px;
font-weight:bold;cursor:pointer;text-decoration:none}.btn:hover{background:#a8161c}
.btn.sec{background:#fff;color:#cd1e25;border:1px solid #cd1e25}.btn.grey{background:#888}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #eee;font-size:14px}
th{color:#777;font-weight:normal;font-size:12px;text-transform:uppercase}
.ok{background:#e7f5e8;border:1px solid #9bd3a0;color:#1e6b26;padding:12px 14px;border-radius:4px;margin-bottom:16px}
.err{background:#fdeaea;border:1px solid #f0a3a3;color:#9b1c1c;padding:12px 14px;border-radius:4px;margin-bottom:16px}
.info{background:#eef4fb;border:1px solid #b9d0ea;color:#24476b;padding:12px 14px;border-radius:4px;margin-bottom:16px}
label{display:block;font-size:13px;color:#555;margin:12px 0 4px}input[type=text],input[type=password],input[type=email]{
width:100%;max-width:420px;padding:9px 10px;border:1px solid #bbb;border-radius:3px;font-size:15px}
.plan{display:flex;justify-content:space-between;align-items:center;gap:16px;border:1px solid #e3e3e3;border-radius:4px;padding:14px 16px;margin-bottom:10px}
.plan.cur{border-color:#cd1e25;background:#fff7f7}.tag{background:#cd1e25;color:#fff;font-size:11px;padding:2px 7px;border-radius:10px;margin-left:6px}
.promo{background:linear-gradient(90deg,#222,#444);color:#fff}.promo a{color:#fff}
dl{display:grid;grid-template-columns:200px 1fr;gap:8px 16px;margin:0}dt{color:#777}dd{margin:0;font-weight:bold}
.login{max-width:440px;margin:40px auto}.actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}
#cookies{position:fixed;left:0;right:0;bottom:0;background:#fff;box-shadow:0 -2px 12px rgba(0,0,0,.2);padding:16px 24px;
display:flex;gap:16px;align-items:center;flex-wrap:wrap;z-index:1000;font-size:13px}#cookies p{flex:1;min-width:260px;margin:0}
footer{text-align:center;color:#999;font-size:12px;padding:20px}
"""

COOKIE_BANNER = """
<div id="cookies"><p><b>Your cookie choices.</b> We use cookies to improve your
experience and measure our audience. You can accept, refuse or customise your choices.</p>
<button class="btn sec" onclick="consent('refus')">Continue without accepting</button>
<button class="btn" onclick="consent('ok')">Accept and close</button></div>
<script>function consent(v){document.cookie='consent='+v+'; path=/; max-age=31536000';
document.getElementById('cookies').remove();}</script>
"""

NAV = [("accueil", "/account/", "Home"), ("forfait", "/account/forfait", "My plan"),
       ("factures", "/account/factures", "Usage & bills"), ("infos", "/account/infos", "My details"),
       ("options", "/account/options", "My options"), ("aide", "/account/aide", "Help")]


def e(x) -> str:
    return html.escape(str(x), quote=True)


def page(title: str, body: str, account: Optional[dict] = None, active: str = "", banner: bool = True) -> str:
    user = ""
    side = ""
    if account:
        user = (f'<div class="user">{e(account["holder"])}<br>Line {e(account["line"])} · '
                f'<a href="/account/logout">Log out</a></div>')
        side = "<nav>" + "".join(
            f'<a href="{href}" class="{"on" if key == active else ""}">{e(label)}</a>' for key, href, label in NAV
        ) + "</nav>"
    content = f'<div class="wrap">{side}<main>{body}</main></div>' if account else body
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} - Free Mobile (mock-up)</title>
<style>{CSS}</style></head><body>
<div class="demo">Demo mock-up for Colette · not affiliated with Free · fictitious account</div>
<header><span class="logo">free<small>mobile</small></span><span class="space">Customer Area</span>{user}</header>
{content}<footer>Colette mock-up · Hackathon H Company × 42AI · <a href="/reset">Reset the demo</a></footer>
{COOKIE_BANNER if banner else ""}</body></html>"""


def plan_block(key: str, account: dict, *, choose: bool) -> str:
    p = PLANS[key]
    cur = key == account["plan"]
    right = ('<span class="muted">Your current plan</span>' if cur else
             f'<a class="btn" href="/account/forfait/recap?offre={key}">Choose this plan</a>') if choose else ""
    return (f'<div class="plan{" cur" if cur else ""}"><div><b>{e(p["name"])}</b>'
            f'{"<span class=tag>Current</span>" if cur else ""}<div class="muted">{e(p["details"])}</div></div>'
            f'<div style="text-align:right"><div class="price">{euros(p["price"])}<span class="muted">/month</span></div>'
            f'{right}</div></div>')


# ---- pages ------------------------------------------------------------------------
def p_login(error: str = "", nxt: str = "/account/") -> str:
    err = f'<div class="err">{e(error)}</div>' if error else ""
    return page("Log in", f"""<div class="login card"><h1>Log in to your Customer Area</h1>{err}
<form method="post" action="/account/login"><input type="hidden" name="next" value="{e(nxt)}">
<label for="login">Customer ID (8 digits)</label><input type="text" id="login" name="login" autocomplete="username" inputmode="numeric">
<label for="password">Password</label><input type="password" id="password" name="password" autocomplete="current-password">
<label style="display:flex;gap:8px;align-items:center;color:#333"><input type="checkbox" name="remember" value="1"> Stay logged in</label>
<div class="actions"><button class="btn" type="submit">Log in</button></div>
<p class="muted" style="margin-top:16px"><a href="#">Forgot your ID or password?</a></p></form></div>""")


def p_home(a: dict) -> str:
    plan = PLANS[a["plan"]]
    last = invoices(a)[0]
    pending = ""
    if a.get("pending_plan"):
        pending = (f'<div class="info">Plan change scheduled: <b>{e(PLANS[a["pending_plan"]]["name"])}</b> '
                   f'starting {date_en(first_of_next_month())}.</div>')
    return page("Home", f"""<h1>Hello {e(a["holder"].split()[0])},</h1>{pending}
<div class="grid">
<div class="card"><h2>My plan</h2><b>{e(plan["name"])}</b><div class="price">{euros(plan["price"])}<span class="muted">/month</span></div>
<p class="muted">{e(plan["details"])}</p><a class="btn sec" href="/account/forfait">Manage my plan</a></div>
<div class="card"><h2>My latest bill</h2><p>Bill for {e(last["period"])}</p><div class="price">{euros(last["amount"])}</div>
<p class="muted">Issued on {date_en(last["issued"])} · Paid by direct debit</p><a class="btn sec" href="/account/factures">See my bills</a></div>
<div class="card"><h2>My usage</h2><p>Data: <b>42.7 GB</b> / 300 GB</p><p>Calls: unlimited · Texts: unlimited</p>
<p class="muted">Since the 1st of the month</p></div>
<div class="card promo"><h2>New: the Max option</h2><p>More data abroad and included services.</p>
<a href="/account/options">Learn more</a></div>
</div>""", a, "accueil")


def p_forfait(a: dict) -> str:
    pending = ""
    if a.get("pending_plan"):
        pending = (f'<div class="info">Change scheduled to <b>{e(PLANS[a["pending_plan"]]["name"])}</b> '
                   f'on {date_en(first_of_next_month())}.</div>')
    return page("My plan", f"""<h1>My plan</h1>{pending}<div class="card"><h2>Current plan</h2>
{plan_block(a["plan"], a, choose=False)}<p class="muted">Line {e(a["line"])} · Commitment: no commitment</p>
<div class="actions"><a class="btn" href="/account/forfait/changer">Change plan</a>
<a class="btn sec" href="/account/options">Manage my options</a></div></div>""", a, "forfait")


def p_changer(a: dict) -> str:
    blocks = "".join(plan_block(k, a, choose=True) for k in PLANS)
    return page("Change plan", f"""<h1>Change plan</h1><div class="card">
<p>Choose your new plan. The change will take effect on <b>{date_en(first_of_next_month())}</b>.</p>
{blocks}</div><a href="/account/forfait">← Back to my plan</a>""", a, "forfait")


def p_recap(a: dict, key: str) -> str:
    new, old = PLANS[key], PLANS[a["plan"]]
    start = date_en(first_of_next_month())
    return page("Summary", f"""<h1>Summary of your plan change</h1><div class="card">
<dl><dt>Current plan</dt><dd>{e(old["name"])} — {euros(old["price"])}/month</dd>
<dt>New plan</dt><dd>{e(new["name"])} — {euros(new["price"])}/month</dd>
<dt>Effective date</dt><dd>{start}</dd><dt>Line</dt><dd>{e(a["line"])}</dd></dl>
<p class="muted" style="margin-top:16px">By confirming, you accept the terms and conditions and the price list of the new plan.
No change fee.</p>
<form method="post" action="/account/forfait/valider"><input type="hidden" name="offre" value="{e(key)}">
<div class="actions"><button class="btn" type="submit">Confirm plan change</button>
<a class="btn grey" href="/account/forfait/changer">Cancel</a></div></form></div>""", a, "forfait")


def p_confirmation(a: dict) -> str:
    key = a.get("pending_plan") or a["plan"]
    return page("Confirmation", f"""<h1>Your request has been recorded</h1>
<div class="ok">Your change to the <b>{e(PLANS[key]["name"])}</b> ({euros(PLANS[key]["price"])}/month) will take effect on
<b>{date_en(first_of_next_month())}</b>. A confirmation email has been sent to {e(a["email"])}.</div>
<a class="btn sec" href="/account/">Back to home</a>""", a, "forfait")


def p_factures(a: dict) -> str:
    rows = "".join(
        f'<tr><td>{e(i["period"])}</td><td>{date_en(i["issued"])}</td><td>{e(i["id"])}</td>'
        f'<td>{euros(i["amount"])}</td><td><a href="/account/factures/{i["id"]}.pdf">Download (PDF)</a></td></tr>'
        for i in invoices(a))
    return page("Usage & bills", f"""<h1>Usage &amp; bills</h1>
<div class="card"><h2>My bills</h2><table><tr><th>Period</th><th>Issued on</th><th>No.</th><th>Amount</th><th></th></tr>
{rows}</table></div><div class="card"><h2>My usage this month</h2><p>Data: 42.7 GB · Calls: 3h12 · Texts: 87</p></div>""",
                a, "factures")


def p_infos(a: dict, ok: bool = False) -> str:
    msg = '<div class="ok">Your contact details have been updated.</div>' if ok else ""
    return page("My details", f"""<h1>My details</h1>{msg}<div class="card"><h2>My contact details</h2>
<dl><dt>Account holder</dt><dd>{e(a["holder"])}</dd><dt>Postal address</dt><dd>{e(a["address"])}<br>{e(a["postcode"])} {e(a["city"])}</dd>
<dt>Email address</dt><dd>{e(a["email"])}</dd><dt>Contact phone</dt><dd>{e(a["contact_phone"])}</dd></dl>
<div class="actions"><a class="btn" href="/account/infos/modifier">Edit my contact details</a></div></div>
<div class="card"><h2>Password</h2><p class="muted">For your security, change your password regularly.</p>
<a class="btn sec" href="#">Change my password</a></div>""", a, "infos")


def p_modifier(a: dict, values: Optional[dict] = None, error: str = "") -> str:
    v = values or a
    err = f'<div class="err">{e(error)}</div>' if error else ""

    def field(name: str, label: str, kind: str = "text") -> str:
        return (f'<label for="{name}">{label}</label>'
                f'<input type="{kind}" id="{name}" name="{name}" value="{e(v.get(name, ""))}">')

    return page("Edit my contact details", f"""<h1>Edit my contact details</h1>{err}<div class="card">
<p class="muted">The line holder ({e(a["holder"])}) cannot be changed online.</p>
<form method="post" action="/account/infos/modifier">
{field("address", "Address (number and street)")}{field("postcode", "Postcode")}{field("city", "City")}
{field("email", "Email address", "email")}{field("contact_phone", "Contact phone")}
<div class="actions"><button class="btn" type="submit">Save changes</button>
<a class="btn grey" href="/account/infos">Cancel</a></div></form></div>""", a, "infos")


def p_simple(a: dict, title: str, active: str, text: str) -> str:
    return page(title, f'<h1>{e(title)}</h1><div class="card"><p>{text}</p></div>', a, active)


# ---- server ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    store: Store
    cookie_banner = True
    server_version = "ColetteDemo/1.0"

    def log_message(self, fmt, *args):  # silent (Colette's logs are enough)
        pass

    # -- helpers
    def _cookies(self) -> SimpleCookie:
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie") or "")
        except Exception:
            pass
        return c

    def _logged_in(self) -> bool:
        c = self._cookies().get("fm_session")
        return c is not None and hmac.compare_digest(c.value, self.store.token())

    def _banner(self) -> bool:
        return self.cookie_banner and "consent" not in self._cookies()

    def _send(self, body, status: int = 200, ctype: str = "text/html; charset=utf-8",
              headers: Optional[dict] = None) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _redirect(self, to: str, cookie: Optional[str] = None) -> None:
        self.send_response(303)
        self.send_header("Location", to)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _form(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        return {k: v[0].strip() for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def _page(self, html_text: str, status: int = 200) -> None:
        if not self._banner():
            html_text = html_text.replace(COOKIE_BANNER, "")
        self._send(html_text, status)

    # -- routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path, q = url.path.rstrip("/") or "/", parse_qs(url.query)
        a = self.store.account
        if path in ("/", "/account"):
            path = "/account/home"
        if path == "/favicon.ico":
            return self._send(b"", 204, "image/x-icon")
        if path == "/reset":
            self.store.reset()
            return self._redirect("/account/login", "fm_session=; Path=/; Max-Age=0")
        if path == "/account/login":
            return self._page(p_login(nxt=(q.get("next") or ["/account/"])[0]))
        if path == "/account/logout":
            return self._redirect("/account/login", "fm_session=; Path=/; Max-Age=0")
        if not self._logged_in():
            return self._redirect("/account/login?next=" + quote(self.path))

        with self.store.lock:
            if path == "/account/home":
                return self._page(p_home(a))
            if path == "/account/forfait":
                return self._page(p_forfait(a))
            if path == "/account/forfait/changer":
                return self._page(p_changer(a))
            if path == "/account/forfait/recap":
                key = (q.get("offre") or [""])[0]
                if key not in PLANS or key == a["plan"]:
                    return self._redirect("/account/forfait/changer")
                return self._page(p_recap(a, key))
            if path == "/account/forfait/confirmation":
                return self._page(p_confirmation(a))
            if path == "/account/factures":
                return self._page(p_factures(a))
            m = re.fullmatch(r"/account/factures/(FM\d+)\.pdf", path)
            if m:
                inv = next((i for i in invoices(a) if i["id"] == m.group(1)), None)
                if inv is None:
                    return self._send("Bill not found", 404, "text/plain; charset=utf-8")
                self.store.log(f"bill {inv['id']} downloaded")
                self.store.save()
                return self._send(invoice_pdf(a, inv), 200, "application/pdf", {
                    "Content-Disposition": f'attachment; filename="Bill_FreeMobile_{inv["id"]}.pdf"'})
            if path == "/account/infos":
                return self._page(p_infos(a, ok="ok" in q))
            if path == "/account/infos/modifier":
                return self._page(p_modifier(a))
            if path == "/account/options":
                return self._page(p_simple(a, "My options", "options",
                                           "No active options on your line. Options will be available here soon."))
            if path == "/account/aide":
                return self._page(p_simple(a, "Help", "aide",
                                           "Need help? Call 3244 (free service + price of a call)."))
        self._page(page("Page not found", "<div class='card'><h1>Page not found</h1>"
                        "<a href='/account/'>Back to home</a></div>", a if self._logged_in() else None), 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        f = self._form()
        if path == "/account/login":
            nxt = f.get("next") or "/account/"
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/account/"
            if f.get("login", "").replace(" ", "") == DEMO_LOGIN and f.get("password") == DEMO_PASSWORD:
                age = "; Max-Age=2592000" if f.get("remember") else ""
                return self._redirect(nxt, f"fm_session={self.store.token()}; Path=/; HttpOnly; SameSite=Lax{age}")
            return self._page(p_login("Incorrect ID or password.", nxt), 401)
        if not self._logged_in():
            return self._redirect("/account/login")

        with self.store.lock:
            a = self.store.account
            if path == "/account/forfait/valider":
                key = f.get("offre", "")
                if key in PLANS and key != a["plan"]:
                    a["pending_plan"] = key
                    self.store.log(f"plan changed to {PLANS[key]['name']}")
                    self.store.save()
                return self._redirect("/account/forfait/confirmation")
            if path == "/account/infos/modifier":
                v = {k: f.get(k, "") for k in ("address", "postcode", "city", "email", "contact_phone")}
                error = ""
                if not all(v.values()):
                    error = "All fields are required."
                elif not re.fullmatch(r"\d{5}", v["postcode"]):
                    error = "The postcode must contain 5 digits."
                elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["email"]):
                    error = "The email address is not valid."
                elif not re.fullmatch(r"(?:\+33|0)\d{9}", re.sub(r"[\s.\-]", "", v["contact_phone"])):
                    error = "The phone number is not valid."
                if error:
                    return self._page(p_modifier(a, v, error), 400)
                a.update(v)
                self.store.log("contact details updated")
                self.store.save()
                return self._redirect("/account/infos?ok=1")
        self._send("Not found", 404, "text/plain; charset=utf-8")


def make_server(port: int = DEFAULT_PORT, host: str = "localhost", cookie_banner: bool = True,
                store: Optional[Store] = None) -> ThreadingHTTPServer:
    handler = type("DemoHandler", (Handler,), {"store": store or Store(), "cookie_banner": cookie_banner})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def start_in_thread(port: int = DEFAULT_PORT, cookie_banner: bool = True) -> tuple[ThreadingHTTPServer, str]:
    """Starts the mock-up in the background. Returns (server, customer area URL)."""
    server = make_server(port, cookie_banner=cookie_banner)
    threading.Thread(target=server.serve_forever, name="demo-site", daemon=True).start()
    return server, f"http://localhost:{port}/account/"


# ---- version en ligne (Vercel) : état du compte dans un cookie signé, un compte par visiteur ----
import base64  # noqa: E402
import os  # noqa: E402

WIDGET_PATH = ROOT / "colette" / "static" / "widget.js"
STATE_COOKIE = "fm_acct"
AGENT_COOKIE = "colette_agent"  # navigateur de l'agent H (cloud) : pas de bulle Colette dedans


class CookieStore:
    """Même interface que Store, mais l'état vit dans un cookie signé (serverless, sans disque)."""

    def __init__(self, cookies: SimpleCookie) -> None:
        self.lock = threading.Lock()
        self.secret = os.getenv("COLETTE_DEMO_SECRET", "colette-demo-secret")
        self.dirty = False
        self.data = {"account": self._load(cookies.get(STATE_COOKIE))}

    def _sign(self, raw: bytes) -> str:
        return hmac.new(self.secret.encode(), raw, hashlib.sha256).hexdigest()[:32]

    def _load(self, morsel) -> dict:
        if morsel is not None:
            try:
                payload, sig = morsel.value.rsplit(".", 1)
                raw = base64.urlsafe_b64decode(payload.encode())
                if hmac.compare_digest(sig, self._sign(raw)):
                    acct = json.loads(raw)
                    return {**copy.deepcopy(DEFAULT_ACCOUNT), **acct}
            except Exception:
                pass
        return copy.deepcopy(DEFAULT_ACCOUNT)

    @property
    def account(self) -> dict:
        return self.data["account"]

    def token(self) -> str:
        return hmac.new(self.secret.encode(), DEMO_LOGIN.encode(), hashlib.sha256).hexdigest()

    def log(self, what: str) -> None:
        h = self.account.setdefault("history", [])
        h.append({"at": dt.datetime.now().isoformat(timespec="seconds"), "what": what})
        del h[:-5]

    def save(self) -> None:
        self.dirty = True

    def reset(self) -> None:
        self.data["account"] = copy.deepcopy(DEFAULT_ACCOUNT)
        self.dirty = True

    def cookie(self) -> str:
        raw = json.dumps(self.account, ensure_ascii=False, separators=(",", ":")).encode()
        value = base64.urlsafe_b64encode(raw).decode() + "." + self._sign(raw)
        return f"{STATE_COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400"


class CloudHandler(Handler):
    """Maquette servie sans disque (Vercel). Avec COLETTE_BACKEND_URL, chaque page charge la bulle
    Colette (widget.js) reliée au backend hébergé (voix + agent H en navigateur cloud)."""

    def _restore_path(self) -> None:
        """Vercel réécrit toute URL vers /api/index?__path=/<chemin> : on retrouve le vrai chemin."""
        u = urlparse(self.path)
        q = parse_qs(u.query, keep_blank_values=True)
        if "__path" not in q:
            return
        path = q.pop("__path")[0] or "/"
        if not path.startswith("/"):
            path = "/" + path
        rest = "&".join(f"{quote(k)}={quote(v)}" for k, vs in q.items() for v in vs)
        self.path = path + ("?" + rest if rest else "")

    def _prepare(self) -> None:
        self._restore_path()
        self.store = CookieStore(self._cookies())  # type: ignore[assignment]
        self._agent = "agent=1" in (urlparse(self.path).query or "") or AGENT_COOKIE in self._cookies()

    def do_GET(self):
        self._prepare()
        path = urlparse(self.path).path
        if path == "/colette/widget.js":
            return self._send(WIDGET_PATH.read_bytes(), 200, "application/javascript; charset=utf-8")
        if path == "/healthz":
            return self._send("ok", 200, "text/plain; charset=utf-8")
        if path == "/colette/handoff":  # la bulle demande un jeton pour partager la session avec l'agent
            if not self._logged_in():
                return self._send('{"error":"not_logged_in"}', 401, "application/json")
            exp = int(dt.datetime.now().timestamp()) + 300
            tok = f"{exp}.{self.store._sign(f'claim:{exp}'.encode())[:20]}"
            return self._send(json.dumps({"token": tok}), 200, "application/json")
        if path == "/colette/claim":  # navigateur de l'agent : reprend la session de la personne
            qs = parse_qs(urlparse(self.path).query)
            t = (qs.get("t") or [""])[0]
            nxt = (qs.get("next") or ["/account/"])[0]
            if not nxt.startswith("/account") or "//" in nxt or nxt.startswith("/account/log"):
                nxt = "/account/"
            exp, _, sig = t.partition(".")
            ok = exp.isdigit() and int(exp) >= dt.datetime.now().timestamp() and \
                hmac.compare_digest(sig, self.store._sign(f"claim:{exp}".encode())[:20])
            if not ok:
                return self._redirect("/account/login?agent=1")
            sep = "&" if "?" in nxt else "?"
            return self._redirect(nxt + sep + "agent=1",
                                  f"fm_session={self.store.token()}; Path=/; HttpOnly; SameSite=Lax")
        return super().do_GET()

    def do_POST(self):
        self._prepare()
        return super().do_POST()

    def end_headers(self):
        store = getattr(self, "store", None)
        if isinstance(store, CookieStore) and store.dirty:
            self.send_header("Set-Cookie", store.cookie())
        if "agent=1" in (urlparse(self.path).query or ""):
            self.send_header("Set-Cookie", f"{AGENT_COOKIE}=1; Path=/; SameSite=Lax")
        super().end_headers()

    def _page(self, html_text: str, status: int = 200) -> None:
        backend = os.getenv("COLETTE_BACKEND_URL", "").strip().rstrip("/")
        if backend and not getattr(self, "_agent", False):
            tag = (f'<script>window.COLETTE_BACKEND={json.dumps(backend)};</script>'
                   '<script src="/colette/widget.js" defer></script>')
            html_text = html_text.replace("</body>", tag + "</body>")
        super()._page(html_text, status)
