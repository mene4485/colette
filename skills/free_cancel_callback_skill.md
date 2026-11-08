# Cancel a booked callback — demo site

Use this skill when the user asks to cancel a callback from customer service they booked earlier.

## Where
- http://localhost:8000/account/ → left menu "Assistance" → card "Être rappelé gratuitement"
  (direct page: http://localhost:8000/account/aide).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Assistance". Find the box "Un conseiller vous rappellera au <number> <slot> (motif : <reason>).".
   If there is no such box (the callback form is shown instead), stop and answer that no callback is booked.
3. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Cancel callback: <slot>, at <number> (reason: <reason>)."
4. Only if the reply says the user approved: click "Annuler le rappel".
   If the user refused: click nothing and answer that the callback is kept.
5. Check that a green box says "Votre demande de rappel a été annulée.", then answer with it.

## Never (in this task)
- Never book a new callback unless the task asks for it (then use the callback request skill).
- Never click "Annuler le rappel" before `confirm_change` replied that the user approved.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
