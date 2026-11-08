# Ask customer service to call back (être rappelé) — demo site

The user must say they want to be called back. The reason, the time slot and the number come from the
user's task:
- reason: one of the list "Ma facture", "Mon forfait", "Un problème technique", "Autre";
- time slot: one of the slots the list offers (for example "Demain de 14h à 16h");
- number: the line number already filled in, unless the task gives another one.
If the reason or the time slot is missing, or the wanted slot is not in the list, do not choose:
answer with the reasons and the slots the page offers, and stop.

## Where
- http://localhost:8000/account/ → left menu "Assistance" → card "Être rappelé gratuitement"
  (direct page: http://localhost:8000/account/aide).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Assistance". If a box already says "Un conseiller vous rappellera au …", stop and answer with
   the booked slot (only one callback at a time; use the cancel callback skill first if the user wants another).
3. In "Motif de votre demande", choose the reason from the task.
4. In "Créneau de rappel", choose the slot from the task.
5. In "Numéro à rappeler", keep the number shown, or clear it and type the number from the task
   (check it digit by digit).
6. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Callback request: <reason>, <slot>, at <number>."
7. Only if the reply says the user approved: click "Demander à être rappelé".
   If the user refused: click nothing and answer that no callback was requested.
8. Check the result:
   - A green box "Un conseiller vous rappellera au <number> <slot> (motif : <reason>).": answer with it.
   - A red message ("Le numéro à rappeler n'est pas valide.", "Choisissez un motif et un créneau dans les
     listes."): answer with the message and stop.

## Never (in this task)
- Never choose a reason or a time slot the task did not give.
- Never click "Demander à être rappelé" before `confirm_change` replied that the user approved.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
