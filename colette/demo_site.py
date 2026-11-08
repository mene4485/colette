"""Maquette locale de l'espace abonné Free Mobile, avec un compte fictif, pour la démo Colette.

Sert sur http://localhost:8000 (bibliothèque standard uniquement). Démarches possibles
(une fiche par démarche dans skills/) :
- se connecter / se déconnecter ; bandeau cookies ;
- consulter son forfait ; changer de forfait (offres → récapitulatif → « Valider le changement ») ;
  annuler un changement de forfait programmé ;
- consulter sa consommation ; consulter ses factures ; télécharger une facture (PDF généré à la volée) ;
- consulter ses coordonnées ; modifier adresse postale, e-mail, téléphone de contact ;
  modifier son mot de passe ;
- consulter ses options ; activer / désactiver une option ;
- service client : numéro et horaires ; demander à être rappelé ; annuler le rappel.

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
    "2e": {"name": "Forfait 2€", "price": 2.00, "data_go": 0.05, "europe_go": 0,
           "details": "2h d'appels · SMS et MMS illimités · 50 Mo d'internet"},
    "serie": {"name": "Série Free 120 Go", "price": 9.99, "data_go": 120, "europe_go": 12,
              "details": "Appels, SMS et MMS illimités · 120 Go en 4G"},
    "5g": {"name": "Forfait Free 5G 300 Go", "price": 19.99, "data_go": 300, "europe_go": 35,
           "details": "Appels, SMS et MMS illimités · 300 Go en 5G · 35 Go depuis l'Europe"},
    "max": {"name": "Forfait Free 5G Max 350 Go", "price": 29.99, "data_go": 350, "europe_go": 35,
            "details": "Appels, SMS et MMS illimités · 350 Go en 5G · 35 Go depuis 100 destinations"},
}

OPTIONS = {
    "messagerie": {"name": "Messagerie vocale visuelle", "price": 0.0,
                   "details": "Écoutez vos messages vocaux dans l'ordre de votre choix."},
    "blocage": {"name": "Blocage des numéros surtaxés", "price": 0.0,
                "details": "Empêche les appels et SMS vers les numéros payants (08, 3BIS…)."},
    "data_europe": {"name": "Option Data Europe +10 Go", "price": 5.00,
                    "details": "10 Go de plus chaque mois, à utiliser depuis l'Europe."},
    "international": {"name": "Option Appels Internationaux", "price": 3.99,
                      "details": "Appels illimités vers les fixes de 100 destinations."},
    "max": {"name": "Option Max", "price": 9.99,
            "details": "35 Go depuis 100 destinations et des services de streaming inclus."},
}

CALLBACK_REASONS = ["Ma facture", "Mon forfait", "Un problème technique", "Autre"]
CALLBACK_SLOTS = [(10, 12), (14, 16), (18, 20)]  # créneaux de rappel, heures

# Consommation fictive du mois en cours (affichée telle quelle).
USAGE = {"data_go": 42.7, "europe_go": 1.2, "calls": "3h12", "sms": 87, "mms": 4, "extra": 0.0}

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
    "password": DEMO_PASSWORD,
    "options": ["messagerie"],
    "callback": None,  # {"reason", "slot", "phone"} : rappel programmé par le service client
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
                # compte enregistré par une version précédente : on complète les champs ajoutés depuis
                data["account"] = {**copy.deepcopy(DEFAULT_ACCOUNT), **data["account"]}
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


def callback_slots(now: Optional[dt.datetime] = None) -> list[str]:
    """Les 4 prochains créneaux de rappel (lundi–samedi), ex. « Aujourd'hui de 14h à 16h »."""
    now = now or dt.datetime.now()
    out, day = [], now.date()
    while len(out) < 4:
        if day.weekday() < 6:  # pas le dimanche
            for start, end in CALLBACK_SLOTS:
                if day > now.date() or start > now.hour:
                    if day == now.date():
                        label = "Aujourd'hui"
                    elif day == now.date() + dt.timedelta(days=1):
                        label = "Demain"
                    else:
                        label = f"Le {date_fr(day)}"
                    out.append(f"{label} de {start}h à {end}h")
                    if len(out) == 4:
                        break
        day += dt.timedelta(days=1)
    return out


def go(x: float) -> str:
    return (f"{x:.1f}".replace(".", ",") + " Go") if x >= 1 else f"{round(x * 1000)} Mo"


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
label{display:block;font-size:13px;color:#555;margin:12px 0 4px}select,input[type=text],input[type=password],input[type=email]{
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
<div class="card"><h2>Ma consommation</h2><p>Internet : <b>{go(USAGE["data_go"])}</b> / {go(plan["data_go"])}</p>
<p>Appels : illimités · SMS : illimités</p><p class="muted">Depuis le 1er du mois</p>
<a class="btn sec" href="/account/conso">Voir le détail</a></div>
<div class="card promo"><h2>Nouveau : l'option Max</h2><p>Plus de data à l'étranger et des services inclus.</p>
<a href="/account/options">En savoir plus</a></div>
</div>""", a, "accueil")


def p_forfait(a: dict, cancelled: bool = False) -> str:
    pending = ""
    if cancelled:
        pending = '<div class="ok">Le changement de forfait programmé a été annulé. Votre forfait actuel est conservé.</div>'
    if a.get("pending_plan"):
        pending = (f'<div class="info">Changement programmé vers <b>{e(PLANS[a["pending_plan"]]["name"])}</b> '
                   f'le {date_fr(first_of_next_month())}.'
                   '<form method="post" action="/account/forfait/annuler" style="margin-top:10px">'
                   '<button class="btn sec" type="submit">Annuler ce changement</button></form></div>')
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
{rows}</table></div><div class="card"><h2>Ma consommation du mois</h2>
<p>Internet : {go(USAGE["data_go"])} · Appels : {USAGE["calls"]} · SMS : {USAGE["sms"]}</p>
<a class="btn sec" href="/account/conso">Voir le détail de ma consommation</a></div>""", a, "factures")


def p_conso(a: dict) -> str:
    plan = PLANS[a["plan"]]
    today = dt.date.today()
    rows = [
        ("Internet en France", go(USAGE["data_go"]), go(plan["data_go"])),
        ("Internet depuis l'Europe", go(USAGE["europe_go"]), go(plan["europe_go"]) if plan["europe_go"] else "Non inclus"),
        ("Appels", USAGE["calls"], "Illimités" if a["plan"] != "2e" else "2h"),
        ("SMS", str(USAGE["sms"]), "Illimités"),
        ("MMS", str(USAGE["mms"]), "Illimités"),
        ("Hors forfait", euros(USAGE["extra"]), "—"),
    ]
    body = "".join(f"<tr><td>{e(k)}</td><td><b>{e(u)}</b></td><td>{e(q)}</td></tr>" for k, u, q in rows)
    pct = min(100, round(100 * USAGE["data_go"] / plan["data_go"]))
    return page("Ma consommation", f"""<h1>Ma consommation</h1><div class="card">
<h2>Du {date_fr(today.replace(day=1))} au {date_fr(today)}</h2>
<p>Internet en France : <b>{pct} %</b> de votre forfait utilisé.</p>
<table><tr><th>Usage</th><th>Consommé</th><th>Inclus dans le forfait</th></tr>{body}</table>
<p class="muted">Les consommations peuvent apparaître avec un délai de 48 heures.</p></div>
<a href="/account/factures">← Retour à Conso et factures</a>""", a, "factures")


def p_infos(a: dict, ok: bool = False, pwd: bool = False) -> str:
    msg = '<div class="ok">Vos coordonnées ont bien été modifiées.</div>' if ok else ""
    if pwd:
        msg += '<div class="ok">Votre mot de passe a bien été modifié.</div>'
    return page("Mes informations", f"""<h1>Mes informations</h1>{msg}<div class="card"><h2>Mes coordonnées</h2>
<dl><dt>Titulaire</dt><dd>{e(a["holder"])}</dd><dt>Adresse postale</dt><dd>{e(a["address"])}<br>{e(a["postcode"])} {e(a["city"])}</dd>
<dt>Adresse e-mail</dt><dd>{e(a["email"])}</dd><dt>Téléphone de contact</dt><dd>{e(a["contact_phone"])}</dd></dl>
<div class="actions"><a class="btn" href="/account/infos/modifier">Modifier mes coordonnées</a></div></div>
<div class="card"><h2>Mot de passe</h2><p class="muted">Pour votre sécurité, changez régulièrement votre mot de passe.</p>
<a class="btn sec" href="/account/infos/motdepasse">Modifier mon mot de passe</a></div>""", a, "infos")


def p_password(a: dict, error: str = "") -> str:
    err = f'<div class="err">{e(error)}</div>' if error else ""
    return page("Modifier mon mot de passe", f"""<h1>Modifier mon mot de passe</h1>{err}<div class="card">
<p class="muted">Le nouveau mot de passe doit contenir au moins 8 caractères, dont au moins un chiffre.</p>
<form method="post" action="/account/infos/motdepasse">
<label for="current">Mot de passe actuel</label><input type="password" id="current" name="current" autocomplete="current-password">
<label for="new">Nouveau mot de passe</label><input type="password" id="new" name="new" autocomplete="new-password">
<label for="confirm">Confirmer le nouveau mot de passe</label><input type="password" id="confirm" name="confirm" autocomplete="new-password">
<div class="actions"><button class="btn" type="submit">Valider le nouveau mot de passe</button>
<a class="btn grey" href="/account/infos">Annuler</a></div></form></div>""", a, "infos")


def p_options(a: dict, msg: str = "") -> str:
    ok = f'<div class="ok">{e(msg)}</div>' if msg else ""
    rows = []
    for key, o in OPTIONS.items():
        on = key in a["options"]
        price = "Gratuite" if not o["price"] else euros(o["price"]) + "/mois"
        action = ("desactiver", "Désactiver", "btn sec") if on else ("activer", "Activer", "btn")
        rows.append(
            f'<div class="plan{" cur" if on else ""}"><div><b>{e(o["name"])}</b>'
            f'{"<span class=tag>Activée</span>" if on else ""}<div class="muted">{e(o["details"])}</div></div>'
            f'<div style="text-align:right"><div><b>{price}</b></div>'
            f'<div class="muted">{"Activée" if on else "Non activée"}</div>'
            f'<a class="{action[2]}" href="/account/options/recap?option={key}&amp;action={action[0]}">{action[1]}</a>'
            f'</div></div>')
    return page("Mes options", f"""<h1>Mes options</h1>{ok}<div class="card">
<p>Activez ou désactivez des options sur votre ligne {e(a["line"])}. Les options payantes sont ajoutées à votre
prochaine facture, au prorata.</p>{"".join(rows)}</div>""", a, "options")


def p_option_recap(a: dict, key: str, action: str) -> str:
    o = OPTIONS[key]
    on = action == "activer"
    price = "Gratuite" if not o["price"] else euros(o["price"]) + "/mois"
    verb = "Confirmer l'activation" if on else "Confirmer la désactivation"
    return page("Récapitulatif", f"""<h1>{"Activation" if on else "Désactivation"} de l'option</h1><div class="card">
<dl><dt>Option</dt><dd>{e(o["name"])}</dd><dt>Prix</dt><dd>{price}</dd>
<dt>Prise d'effet</dt><dd>Immédiate</dd><dt>Ligne concernée</dt><dd>{e(a["line"])}</dd></dl>
<p class="muted" style="margin-top:16px">{"Le prix est ajouté à votre prochaine facture, au prorata du mois en cours."
    if on and o["price"] else "Aucun frais."}</p>
<form method="post" action="/account/options/valider"><input type="hidden" name="option" value="{e(key)}">
<input type="hidden" name="action" value="{e(action)}">
<div class="actions"><button class="btn" type="submit">{verb}</button>
<a class="btn grey" href="/account/options">Annuler</a></div></form></div>""", a, "options")


def p_aide(a: dict, error: str = "", ok: bool = False, cancelled: bool = False) -> str:
    msg = f'<div class="err">{e(error)}</div>' if error else ""
    if cancelled:
        msg += '<div class="ok">Votre demande de rappel a été annulée.</div>'
    cb = a.get("callback")
    if cb:
        callback = (f'<div class="{"ok" if ok else "info"}">Un conseiller vous rappellera au <b>{e(cb["phone"])}</b> '
                    f'<b>{e(cb["slot"].lower() if not cb["slot"].startswith("Le") else cb["slot"])}</b> '
                    f'(motif : {e(cb["reason"])}).'
                    '<form method="post" action="/account/aide/annuler" style="margin-top:10px">'
                    '<button class="btn sec" type="submit">Annuler le rappel</button></form></div>')
        form = ""
    else:
        callback = ""
        reasons = "".join(f"<option>{e(r)}</option>" for r in CALLBACK_REASONS)
        slots = "".join(f"<option>{e(s)}</option>" for s in callback_slots())
        form = f"""<form method="post" action="/account/aide/rappel">
<label for="reason">Motif de votre demande</label><select id="reason" name="reason">{reasons}</select>
<label for="slot">Créneau de rappel</label><select id="slot" name="slot">{slots}</select>
<label for="phone">Numéro à rappeler</label><input type="text" id="phone" name="phone" value="{e(a["line"])}">
<div class="actions"><button class="btn" type="submit">Demander à être rappelé</button></div></form>"""
    return page("Assistance", f"""<h1>Assistance</h1>{msg}
<div class="card"><h2>Appeler le service client</h2><div class="price">3244</div>
<p>Depuis votre mobile Free : appel gratuit. Depuis un autre téléphone : service gratuit + prix d'un appel.</p>
<p class="muted">Du lundi au samedi, de 8h à 22h.</p></div>
<div class="card"><h2>Être rappelé gratuitement</h2>
<p class="muted">Un conseiller vous rappelle sur le créneau de votre choix.</p>{callback}{form}</div>""", a, "aide")


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
                return self._page(p_forfait(a, cancelled="annule" in q))
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
            if path == "/account/conso":
                return self._page(p_conso(a))
            if path == "/account/infos":
                return self._page(p_infos(a, ok="ok" in q, pwd="pwd" in q))
            if path == "/account/infos/modifier":
                return self._page(p_modifier(a))
            if path == "/account/infos/motdepasse":
                return self._page(p_password(a))
            if path == "/account/options":
                key, act = (q.get("option") or [""])[0], (q.get("ok") or [""])[0]
                msg = ""
                if key in OPTIONS and act in ("activer", "desactiver"):
                    msg = f"L'option « {OPTIONS[key]['name']} » est {'activée' if act == 'activer' else 'désactivée'}."
                return self._page(p_options(a, msg))
            if path == "/account/options/recap":
                key, act = (q.get("option") or [""])[0], (q.get("action") or [""])[0]
                if key not in OPTIONS or act not in ("activer", "desactiver") or \
                        (act == "activer") == (key in a["options"]):
                    return self._redirect("/account/options")
                return self._page(p_option_recap(a, key, act))
            if path == "/account/aide":
                return self._page(p_aide(a, ok="ok" in q, cancelled="annule" in q))
        self._page(page("Page introuvable", "<div class='card'><h1>Page introuvable</h1>"
                        "<a href='/account/'>Retour à l'accueil</a></div>", a if self._logged_in() else None), 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        f = self._form()
        if path == "/account/login":
            nxt = f.get("next") or "/account/"
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/account/"
            if f.get("login", "").replace(" ", "") == DEMO_LOGIN and \
                    hmac.compare_digest(f.get("password", ""), self.store.account["password"]):
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
            if path == "/account/forfait/annuler":
                if a.get("pending_plan"):
                    self.store.log(f"changement vers {PLANS[a['pending_plan']]['name']} annulé")
                    a["pending_plan"] = None
                    self.store.save()
                return self._redirect("/account/forfait?annule=1")
            if path == "/account/infos/motdepasse":
                cur, new, conf = f.get("current", ""), f.get("new", ""), f.get("confirm", "")
                error = ""
                if not hmac.compare_digest(cur, a["password"]):
                    error = "Le mot de passe actuel est incorrect."
                elif len(new) < 8 or not re.search(r"\d", new):
                    error = "Le nouveau mot de passe doit contenir au moins 8 caractères, dont au moins un chiffre."
                elif new != conf:
                    error = "Les deux nouveaux mots de passe ne sont pas identiques."
                elif new == cur:
                    error = "Le nouveau mot de passe doit être différent de l'actuel."
                if error:  # jamais de mot de passe renvoyé dans la page
                    return self._page(p_password(a, error), 400)
                a["password"] = new
                self.store.log("mot de passe modifié")
                self.store.save()
                return self._redirect("/account/infos?pwd=1")
            if path == "/account/options/valider":
                key, act = f.get("option", ""), f.get("action", "")
                if key in OPTIONS and act == "activer" and key not in a["options"]:
                    a["options"].append(key)
                elif key in OPTIONS and act == "desactiver" and key in a["options"]:
                    a["options"].remove(key)
                else:
                    return self._redirect("/account/options")
                self.store.log(f"option {OPTIONS[key]['name']} : {act}")
                self.store.save()
                return self._redirect(f"/account/options?option={key}&ok={act}")
            if path == "/account/aide/rappel":
                reason, slot = f.get("reason", ""), f.get("slot", "")
                phone = f.get("phone", "")
                error = ""
                if reason not in CALLBACK_REASONS or slot not in callback_slots():
                    error = "Choisissez un motif et un créneau dans les listes."
                elif not re.fullmatch(r"(?:\+33|0)\d{9}", re.sub(r"[\s.\-]", "", phone)):
                    error = "Le numéro à rappeler n'est pas valide."
                if error:
                    return self._page(p_aide(a, error=error), 400)
                a["callback"] = {"reason": reason, "slot": slot, "phone": phone}
                self.store.log(f"rappel demandé : {slot}")
                self.store.save()
                return self._redirect("/account/aide?ok=1")
            if path == "/account/aide/annuler":
                if a.get("callback"):
                    a["callback"] = None
                    self.store.log("rappel annulé")
                    self.store.save()
                return self._redirect("/account/aide?annule=1")
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
