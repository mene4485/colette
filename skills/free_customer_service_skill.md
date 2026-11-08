# Find how to call customer service — demo site

Use this skill when the user wants to talk to a person at Free ("appeler le service client",
"le numéro de Free", "parler à un conseiller"). You cannot make the phone call: you give the number,
the cost and the opening hours, and you offer the callback (see the callback request skill).
This task only reads.

## Where
- http://localhost:8000/account/ → left menu "Assistance"
  (direct page: http://localhost:8000/account/aide).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Assistance". In the card "Appeler le service client", read: the number (in red),
   the cost text, and the opening hours.
3. Answer with the number (say it digit by digit: "trois, deux, quatre, quatre"), the cost, and the hours.
   Then say that a free callback can also be requested on this page, and ask nothing else.
4. If a box already says "Un conseiller vous rappellera au …", mention that a callback is already booked,
   with its time slot.

## Never (in this task)
- Never fill or submit the callback form ("Demander à être rappelé") unless the task asks for a callback.
- Never click "Annuler le rappel".
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
