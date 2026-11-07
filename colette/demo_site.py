"""Maquette locale de l'espace abonné Free Mobile, avec un compte fictif, pour la démo Colette.

Sert sur http://localhost:8000 (bibliothèque standard uniquement). Démarches possibles :
- changer de forfait (liste des offres → récapitulatif → « Valider le changement ») ;
- télécharger la facture la plus récente (vrai PDF généré à la volée) ;
- modifier ses coordonnées (adresse, e-mail, téléphone de contact → « Enregistrer »).

Compte de démo : identifiant 12345678, mot de passe colette (affichés nulle part sur le site).
Les modifications sont gardées dans demo_data/account.json ; /reset remet le compte à zéro.
Ce n'est PAS le site de Free : un bandeau « Maquette de démonstration » est affiché sur chaque page.
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
    "2e": {"name": "Forfait 2€", "price": 2.00,
           "details": "2h d'appels · SMS et MMS illimités · 50 Mo d'internet"},
    "serie": {"name": "Série Free 120 Go", "price": 9.99,
              "details": "Appels, SMS et MMS illimités · 120 Go en 4G"},
    "5g": {"name": "Forfait Free 5G 300 Go", "price": 19.99,
           "details": "Appels, SMS et MMS illimités · 300 Go en 5G · 35 Go depuis l'Europe"},
    "max": {"name": "Forfait Free 5G Max 350 Go", "price": 29.99,
            "details": "Appels, SMS et MMS illimités · 350 Go en 5G · 35 Go depuis 100 destinations"},
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

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]


def euros(x: float) -> str:
    return f"{x:.2f}".replace(".", ",") + " €"


def first_of_next_month(today: Optional[dt.date] = None) -> dt.date:
    today = today or dt.date.today()
    return (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)


def date_fr(d: dt.date) -> str:
    return f"{d.day}{'er' if d.day == 1 else ''} {MONTHS[d.month - 1]} {d.year}"


# ---- données du compte ----------------------------------------------------------
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
            self.data["secret"] = secrets.token_hex(16)  # déconnecte tout le monde
            self.save()

    @property
    def account(self) -> dict:
        return self.data["account"]

    def token(self) -> str:
        return hmac.new(self.data["secret"].encode(), DEMO_LOGIN.encode(), hashlib.sha256).hexdigest()

    def log(self, what: str) -> None:
        self.account["history"].append({"at": dt.datetime.now().isoformat(timespec="seconds"), "what": what})


def invoices(account: dict, today: Optional[dt.date] = None) -> list[dict]:
    """Les 6 dernières factures, la plus récente d'abord (facture du mois M émise le 1er du mois M+1)."""
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


# ---- PDF minimal (texte seul, Helvetica, WinAnsi pour les accents et l'€) ------------
def make_pdf(lines: list[tuple[str, int, str]]) -> bytes:
    """lines = [(police "R"|"B", taille, texte)] de haut en bas."""
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
        ("B", 20, "Free Mobile — Facture (maquette de démonstration)"),
        ("R", 10, "Document fictif généré pour la démo Colette. Ce n'est pas une vraie facture."),
        ("R", 11, ""),
        ("B", 13, f"Facture n° {inv['id']}"),
        ("R", 11, f"Période : du {inv['period_start']:%d/%m/%Y} au {inv['period_end']:%d/%m/%Y}"),
        ("R", 11, f"Date d'émission : {inv['issued']:%d/%m/%Y}"),
        ("R", 11, ""),
        ("B", 12, "Titulaire"),
        ("R", 11, account["holder"]),
        ("R", 11, account["address"]),
        ("R", 11, f"{account['postcode']} {account['city']}"),
        ("R", 11, f"Ligne : {account['line']}"),
        ("R", 11, ""),
        ("B", 12, "Détail"),
        ("R", 11, f"{plan['name']} — abonnement mensuel"),
        ("R", 11, f"Montant HT : {euros(ht)}"),
        ("R", 11, f"TVA 20 % : {euros(inv['amount'] - ht)}"),
        ("B", 13, f"Total TTC : {euros(inv['amount'])}"),
        ("R", 11, ""),
        ("R", 10, "Prélevé automatiquement sur votre compte bancaire."),
    ])


# ---- HTML -------------------------------------------------------------------------
CSS = """
*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#f2f2f2;color:#333;font-size:15px}
a{color:#cd1e25}.demo{background:#fff8c5;color:#6b5900;font-size:12px;text-align:center;padding:4px 8px;border-bottom:1px solid #e6d77a}
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
<div id="cookies"><p><b>Vos choix concernant les cookies.</b> Nous utilisons des cookies pour améliorer votre
expérience et mesurer l'audience. Vous pouvez accepter, refuser ou personnaliser vos choix.</p>
<button class="btn sec" onclick="consent('refus')">Continuer sans accepter</button>
<button class="btn" onclick="consent('ok')">Accepter et fermer</button></div>
<script>function consent(v){document.cookie='consent='+v+'; path=/; max-age=31536000';
document.getElementById('cookies').remove();}</script>
"""

NAV = [("accueil", "/account/", "Accueil"), ("forfait", "/account/forfait", "Mon forfait"),
       ("factures", "/account/factures", "Conso et factures"), ("infos", "/account/infos", "Mes informations"),
       ("options", "/account/options", "Mes options"), ("aide", "/account/aide", "Assistance")]


def e(x) -> str:
    return html.escape(str(x), quote=True)


def page(title: str, body: str, account: Optional[dict] = None, active: str = "", banner: bool = True) -> str:
    user = ""
    side = ""
    if account:
        user = (f'<div class="user">{e(account["holder"])}<br>Ligne {e(account["line"])} · '
                f'<a href="/account/logout">Se déconnecter</a></div>')
        side = "<nav>" + "".join(
            f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>' for key, href, label in NAV
        ) + "</nav>"
    content = f'<div class="wrap">{side}<main>{body}</main></div>' if account else body
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} - Free Mobile (maquette)</title>
<style>{CSS}</style></head><body>
<div class="demo">Maquette de démonstration Colette — ce n'est pas le site officiel de Free. Compte et données fictifs.</div>
<header><span class="logo">free<small>mobile</small></span><span class="space">Espace Abonné</span>{user}</header>
{content}<footer>Maquette Colette · Hackathon H Company × 42AI · <a href="/reset">Réinitialiser la démo</a></footer>
{COOKIE_BANNER if banner else ""}</body></html>"""


def plan_block(key: str, account: dict, *, choose: bool) -> str:
    p = PLANS[key]
    cur = key == account["plan"]
    right = ('<span class="muted">Votre forfait actuel</span>' if cur else
             f'<a class="btn" href="/account/forfait/recap?offre={key}">Choisir ce forfait</a>') if choose else ""
    return (f'<div class="plan{" cur" if cur else ""}"><div><b>{e(p["name"])}</b>'
            f'{"<span class=tag>Actuel</span>" if cur else ""}<div class="muted">{e(p["details"])}</div></div>'
            f'<div style="text-align:right"><div class="price">{euros(p["price"])}<span class="muted">/mois</span></div>'
            f'{right}</div></div>')


# ---- pages ------------------------------------------------------------------------
def p_login(error: str = "", nxt: str = "/account/") -> str:
    err = f'<div class="err">{e(error)}</div>' if error else ""
    return page("Connexion", f"""<div class="login card"><h1>Connexion à votre Espace Abonné</h1>{err}
<form method="post" action="/account/login"><input type="hidden" name="next" value="{e(nxt)}">
<label for="login">Identifiant (8 chiffres)</label><input type="text" id="login" name="login" autocomplete="username" inputmode="numeric">
<label for="password">Mot de passe</label><input type="password" id="password" name="password" autocomplete="current-password">
<label style="display:flex;gap:8px;align-items:center;color:#333"><input type="checkbox" name="remember" value="1"> Rester connecté</label>
<div class="actions"><button class="btn" type="submit">Se connecter</button></div>
<p class="muted" style="margin-top:16px"><a href="#">Identifiant ou mot de passe oublié ?</a></p></form></div>""")


def p_home(a: dict) -> str:
    plan = PLANS[a["plan"]]
    last = invoices(a)[0]
    pending = ""
    if a.get("pending_plan"):
        pending = (f'<div class="info">Changement de forfait programmé : <b>{e(PLANS[a["pending_plan"]]["name"])}</b> '
                   f'à partir du {date_fr(first_of_next_month())}.</div>')
    return page("Accueil", f"""<h1>Bonjour {e(a["holder"].split()[0])},</h1>{pending}
<div class="grid">
<div class="card"><h2>Mon forfait</h2><b>{e(plan["name"])}</b><div class="price">{euros(plan["price"])}<span class="muted">/mois</span></div>
<p class="muted">{e(plan["details"])}</p><a class="btn sec" href="/account/forfait">Gérer mon forfait</a></div>
<div class="card"><h2>Ma dernière facture</h2><p>Facture de {e(last["period"])}</p><div class="price">{euros(last["amount"])}</div>
<p class="muted">Émise le {last["issued"]:%d/%m/%Y} · Prélevée automatiquement</p><a class="btn sec" href="/account/factures">Voir mes factures</a></div>
<div class="card"><h2>Ma consommation</h2><p>Internet : <b>42,7 Go</b> / 300 Go</p><p>Appels : illimités · SMS : illimités</p>
<p class="muted">Depuis le 1er du mois</p></div>
<div class="card promo"><h2>Nouveau : l'option Max</h2><p>Plus de data à l'étranger et des services inclus.</p>
<a href="/account/options">En savoir plus</a></div>
</div>""", a, "accueil")


def p_forfait(a: dict) -> str:
    pending = ""
    if a.get("pending_plan"):
        pending = (f'<div class="info">Changement programmé vers <b>{e(PLANS[a["pending_plan"]]["name"])}</b> '
                   f'le {date_fr(first_of_next_month())}.</div>')
    return page("Mon forfait", f"""<h1>Mon forfait</h1>{pending}<div class="card"><h2>Forfait actuel</h2>
{plan_block(a["plan"], a, choose=False)}<p class="muted">Ligne {e(a["line"])} · Engagement : sans engagement</p>
<div class="actions"><a class="btn" href="/account/forfait/changer">Changer de forfait</a>
<a class="btn sec" href="/account/options">Gérer mes options</a></div></div>""", a, "forfait")


def p_changer(a: dict) -> str:
    blocks = "".join(plan_block(k, a, choose=True) for k in PLANS)
    return page("Changer de forfait", f"""<h1>Changer de forfait</h1><div class="card">
<p>Choisissez votre nouveau forfait. Le changement prendra effet le <b>{date_fr(first_of_next_month())}</b>.</p>
{blocks}</div><a href="/account/forfait">← Retour à mon forfait</a>""", a, "forfait")


def p_recap(a: dict, key: str) -> str:
    new, old = PLANS[key], PLANS[a["plan"]]
    start = date_fr(first_of_next_month())
    return page("Récapitulatif", f"""<h1>Récapitulatif de votre changement de forfait</h1><div class="card">
<dl><dt>Forfait actuel</dt><dd>{e(old["name"])} — {euros(old["price"])}/mois</dd>
<dt>Nouveau forfait</dt><dd>{e(new["name"])} — {euros(new["price"])}/mois</dd>
<dt>Date d'effet</dt><dd>{start}</dd><dt>Ligne concernée</dt><dd>{e(a["line"])}</dd></dl>
<p class="muted" style="margin-top:16px">En validant, vous acceptez les conditions générales et la brochure tarifaire du nouveau forfait.
Aucun frais de changement.</p>
<form method="post" action="/account/forfait/valider"><input type="hidden" name="offre" value="{e(key)}">
<div class="actions"><button class="btn" type="submit">Valider le changement de forfait</button>
<a class="btn grey" href="/account/forfait/changer">Annuler</a></div></form></div>""", a, "forfait")


def p_confirmation(a: dict) -> str:
    key = a.get("pending_plan") or a["plan"]
    return page("Confirmation", f"""<h1>Votre demande est enregistrée</h1>
<div class="ok">Votre changement vers le <b>{e(PLANS[key]["name"])}</b> ({euros(PLANS[key]["price"])}/mois) prendra effet le
<b>{date_fr(first_of_next_month())}</b>. Un e-mail de confirmation a été envoyé à {e(a["email"])}.</div>
<a class="btn sec" href="/account/">Retour à l'accueil</a>""", a, "forfait")


def p_factures(a: dict) -> str:
    rows = "".join(
        f'<tr><td>{e(i["period"]).capitalize()}</td><td>{i["issued"]:%d/%m/%Y}</td><td>{e(i["id"])}</td>'
        f'<td>{euros(i["amount"])}</td><td><a href="/account/factures/{i["id"]}.pdf">Télécharger (PDF)</a></td></tr>'
        for i in invoices(a))
    return page("Conso et factures", f"""<h1>Conso et factures</h1>
<div class="card"><h2>Mes factures</h2><table><tr><th>Période</th><th>Émise le</th><th>N°</th><th>Montant</th><th></th></tr>
{rows}</table></div><div class="card"><h2>Ma consommation du mois</h2><p>Internet : 42,7 Go · Appels : 3h12 · SMS : 87</p></div>""",
                a, "factures")


def p_infos(a: dict, ok: bool = False) -> str:
    msg = '<div class="ok">Vos coordonnées ont bien été modifiées.</div>' if ok else ""
    return page("Mes informations", f"""<h1>Mes informations</h1>{msg}<div class="card"><h2>Mes coordonnées</h2>
<dl><dt>Titulaire</dt><dd>{e(a["holder"])}</dd><dt>Adresse postale</dt><dd>{e(a["address"])}<br>{e(a["postcode"])} {e(a["city"])}</dd>
<dt>Adresse e-mail</dt><dd>{e(a["email"])}</dd><dt>Téléphone de contact</dt><dd>{e(a["contact_phone"])}</dd></dl>
<div class="actions"><a class="btn" href="/account/infos/modifier">Modifier mes coordonnées</a></div></div>
<div class="card"><h2>Mot de passe</h2><p class="muted">Pour votre sécurité, changez régulièrement votre mot de passe.</p>
<a class="btn sec" href="#">Changer mon mot de passe</a></div>""", a, "infos")


def p_modifier(a: dict, values: Optional[dict] = None, error: str = "") -> str:
    v = values or a
    err = f'<div class="err">{e(error)}</div>' if error else ""

    def field(name: str, label: str, kind: str = "text") -> str:
        return (f'<label for="{name}">{label}</label>'
                f'<input type="{kind}" id="{name}" name="{name}" value="{e(v.get(name, ""))}">')

    return page("Modifier mes coordonnées", f"""<h1>Modifier mes coordonnées</h1>{err}<div class="card">
<p class="muted">Le titulaire de la ligne ({e(a["holder"])}) ne peut pas être modifié en ligne.</p>
<form method="post" action="/account/infos/modifier">
{field("address", "Adresse (numéro et rue)")}{field("postcode", "Code postal")}{field("city", "Ville")}
{field("email", "Adresse e-mail", "email")}{field("contact_phone", "Téléphone de contact")}
<div class="actions"><button class="btn" type="submit">Enregistrer les modifications</button>
<a class="btn grey" href="/account/infos">Annuler</a></div></form></div>""", a, "infos")


def p_simple(a: dict, title: str, active: str, text: str) -> str:
    return page(title, f'<h1>{e(title)}</h1><div class="card"><p>{text}</p></div>', a, active)


# ---- serveur ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    store: Store
    cookie_banner = True
    server_version = "ColetteDemo/1.0"

    def log_message(self, fmt, *args):  # silencieux (les logs Colette suffisent)
        pass

    # -- utilitaires
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
                    return self._send("Facture introuvable", 404, "text/plain; charset=utf-8")
                self.store.log(f"facture {inv['id']} téléchargée")
                self.store.save()
                return self._send(invoice_pdf(a, inv), 200, "application/pdf", {
                    "Content-Disposition": f'attachment; filename="Facture_FreeMobile_{inv["id"]}.pdf"'})
            if path == "/account/infos":
                return self._page(p_infos(a, ok="ok" in q))
            if path == "/account/infos/modifier":
                return self._page(p_modifier(a))
            if path == "/account/options":
                return self._page(p_simple(a, "Mes options", "options",
                                           "Aucune option active sur votre ligne. Les options seront bientôt disponibles ici."))
            if path == "/account/aide":
                return self._page(p_simple(a, "Assistance", "aide",
                                           "Besoin d'aide ? Appelez le 3244 (service gratuit + prix d'un appel)."))
        self._page(page("Page introuvable", "<div class='card'><h1>Page introuvable</h1>"
                        "<a href='/account/'>Retour à l'accueil</a></div>", a if self._logged_in() else None), 404)

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
            return self._page(p_login("Identifiant ou mot de passe incorrect.", nxt), 401)
        if not self._logged_in():
            return self._redirect("/account/login")

        with self.store.lock:
            a = self.store.account
            if path == "/account/forfait/valider":
                key = f.get("offre", "")
                if key in PLANS and key != a["plan"]:
                    a["pending_plan"] = key
                    self.store.log(f"changement de forfait vers {PLANS[key]['name']}")
                    self.store.save()
                return self._redirect("/account/forfait/confirmation")
            if path == "/account/infos/modifier":
                v = {k: f.get(k, "") for k in ("address", "postcode", "city", "email", "contact_phone")}
                error = ""
                if not all(v.values()):
                    error = "Tous les champs sont obligatoires."
                elif not re.fullmatch(r"\d{5}", v["postcode"]):
                    error = "Le code postal doit contenir 5 chiffres."
                elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["email"]):
                    error = "L'adresse e-mail n'est pas valide."
                elif not re.fullmatch(r"(?:\+33|0)\d{9}", re.sub(r"[\s.\-]", "", v["contact_phone"])):
                    error = "Le numéro de téléphone n'est pas valide."
                if error:
                    return self._page(p_modifier(a, v, error), 400)
                a.update(v)
                self.store.log("coordonnées modifiées")
                self.store.save()
                return self._redirect("/account/infos?ok=1")
        self._send("Introuvable", 404, "text/plain; charset=utf-8")


def make_server(port: int = DEFAULT_PORT, host: str = "localhost", cookie_banner: bool = True,
                store: Optional[Store] = None) -> ThreadingHTTPServer:
    handler = type("DemoHandler", (Handler,), {"store": store or Store(), "cookie_banner": cookie_banner})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def start_in_thread(port: int = DEFAULT_PORT, cookie_banner: bool = True) -> tuple[ThreadingHTTPServer, str]:
    """Démarre la maquette en tâche de fond. Renvoie (serveur, URL de l'espace abonné)."""
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
