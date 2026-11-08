# Log in to the Free Mobile customer area (demo site)

Use this skill whenever a page shows "Connexion à votre Espace Abonné", or when any other skill says
"log in first". It is the login step of every other Free Mobile skill.

## Where
- Demo customer area: http://localhost:8000/account/ (any page redirects to the login page when you are logged out).
- Login page: http://localhost:8000/account/login
- Pages are in French.

## Steps
1. If a cookie banner appears at the bottom of the page, click "Continuer sans accepter".
2. On the login page, call `fill_free_login` (no arguments). It fills "Identifiant (8 chiffres)" and
   "Mot de passe" without showing them to you. Never type an identifier or a password yourself.
3. Leave "Rester connecté" as it is.
4. Click "Se connecter".
5. Check the result:
   - The page shows "Bonjour <first name>," and a left menu (Accueil, Mon forfait, …): you are logged in.
     Continue the task you were doing.
   - The page shows "Identifiant ou mot de passe incorrect.": do not try again. Stop and answer that the
     login failed.

## Never (in this task)
- Never type, guess or repeat an identifier, password or code in a field or in your answer.
- Never click "Identifiant ou mot de passe oublié ?".
- Never try to log in more than once.
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## If something is not as described
- This demo site has no SMS code step. If a page asks for a code anyway, stop and describe what you see.
