---
name: demo-options
description: Use when the person wants to see, activate (turn on, add) or deactivate (turn off, remove) an option on their line (visual voicemail, premium-rate number blocking, Europe data, international calls, Max option) on the Free Mobile demo customer area.
label: My options
ask: I'd like to see or change my options.
keywords: option | options | voicemail | number blocking | international calls
steps: Open your customer area | Log in | Open your options | Choose the option with you | Confirm with your approval
steps_view: Open your customer area | Log in | Open your options | Read your options
order: 4
---
# See, activate or deactivate an option — demo customer area

The page offers exactly these options:
- "Visual voicemail" — Free
- "Premium-rate number blocking" — Free
- "Europe Data +10 GB option" — €5.00/month
- "International Calls option" — €3.99/month
- "Max option" — €9.99/month

## Where
- Left menu "My options". "My plan" → "Manage my options" and the home card "New: the Max option" →
  "Learn more" lead to the same page.

## See the options (the person only wants to know)
1. Open "My options". For each option read its name, the grey text, its price ("Free" or "<price>/month")
   and its state ("Active" or "Not active").
2. Answer: the active options first, then the others with their prices, one simple sentence each.
   Click nothing else. Never recommend an option yourself.

## Activate an option
1. The option must be named by the person. If she did not name exactly one option of the list, call
   `ask_user` with a short question listing the options and their prices, and use the one she names.
2. If it already shows "Active", answer that it is already active and stop.
3. Click "Activate" in that option's row.
4. On "Activate an option", read "Option", "Price", "Takes effect" and the notice below.
5. Call `confirm_change` with `costs_money` = true if the price is not "Free" (false otherwise), and a
   summary such as: "activate the Europe Data +10 GB option, €5.00 per month, starting immediately".
6. Only if the reply starts with "Approved": click "Confirm activation".
   If refused: click "Cancel" and answer that the option was not activated.
7. Check the green box "The option “<name>” is activated." and answer with it.

## Deactivate an option
1. The option must be named by the person and show "Active". If not, ask with `ask_user` (listing the
   active options) or answer that it is not active.
2. Click "Deactivate" in that option's row.
3. On "Deactivate an option", read "Option", "Price", "Takes effect".
4. Call `confirm_change` with `costs_money` = false and a summary such as:
   "deactivate the Visual voicemail option, starting immediately".
5. Only if the reply starts with "Approved": click "Confirm deactivation".
   If refused: click "Cancel" and answer that the option is still active.
6. Check the green box "The option “<name>” is deactivated." and answer with it.

## Never
- Never activate or deactivate an option the person did not name, and never a second one.
- Never click "Confirm activation" or "Confirm deactivation" before `confirm_change` replied "Approved".
- Never change the plan, personal details, or click "Reset the demo" or "Log out".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
