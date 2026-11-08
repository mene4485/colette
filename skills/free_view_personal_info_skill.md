# Check personal details (coordonnées) — demo site

Use this skill when the user asks which details are registered: holder name, postal address, contact
email, contact phone. This task only reads. To change a detail, use the matching change skill.

## Where
- http://localhost:8000/account/ → left menu "Mes informations"
  (direct page: http://localhost:8000/account/infos).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Mes informations". Under "Mes coordonnées", read: "Titulaire", "Adresse postale",
   "Adresse e-mail", "Téléphone de contact".
3. Answer with the details the user asked about, exactly as shown.

## Never (in this task)
- Never click "Modifier mes coordonnées" or "Modifier mon mot de passe".
- Never read out or write a password: the page never shows it.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
