---
name: demo-personal-info
description: Use when the person wants to see or change their postal address, contact email or contact phone (contact details, personal information) on the Free Mobile demo customer area.
label: My details
ask: I'd like to see or change my contact details.
keywords: details | address | email | e-mail | phone | contact
steps: Open your customer area | Log in | Open your details | Edit your details | Confirm with your approval
steps_view: Open your customer area | Log in | Open your details | Read your details
order: 3
---
# See or change contact details — demo customer area

If the person only wants to SEE a detail, open "My details", read it and answer. Change nothing.
New values come from the task. If a piece is missing, ask only for it with `ask_user`, one short
question at a time (number and street, then postcode, then city), keeping what was already said.
Never invent a value.

## Where
- Left menu "My details" → section "My contact details" → button "Edit my contact details".
- The form has plain text fields: "Address (number and street)", "Postcode", "City",
  "Email address", "Contact phone". Only change the fields the person asked for.

## Steps
1. Open "My details" and write down the current value of the detail to change.
2. Click "Edit my contact details".
3. For each field to change: click it, select all its text and replace it with the new value. Check it.
4. Call `confirm_change` with a short English summary, e.g.
   "replace the address 12 rue des Lilas, 75020 Paris with 3 place de la République, 75003 Paris".
5. Only if the reply starts with "Approved": click "Save changes".
   If refused: click "Cancel" and answer that nothing was changed.
6. If the page shows a red error, fix that field (ask the person if needed) and try again.
7. Answer with what the page shows ("Your contact details have been updated.").

## Never
- Never change the holder name, the password, the plan or the options.
- Never click "Save changes" before `confirm_change` replied "Approved".

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
