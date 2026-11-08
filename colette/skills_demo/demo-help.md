---
name: demo-help
description: Use when the person wants to talk to someone at Free: customer service phone number and opening hours, ask an advisor to call her back (callback), or cancel a callback she booked, on the Free Mobile demo customer area.
label: Talk to an advisor
ask: I'd like an advisor from Free to call me back.
keywords: call me back | callback | call back | customer service | advisor | talk to someone | speak to someone
steps: Open your customer area | Log in | Open the help page | Fill in the callback request | Confirm with your approval
steps_view: Open your customer area | Log in | Open the help page | Read the number and the hours
order: 5
---
# Customer service, callback, cancel a callback — demo customer area

You cannot make a phone call yourself. You can give the number and the hours, book a free callback,
or cancel a booked callback.

## Where
- Left menu "Help". Card "Call customer service" (number, cost, hours) and card "Get a free callback".

## Customer service number (the person only wants to know)
1. Open "Help". In "Call customer service" read the number (in red), the cost text and the hours.
2. Answer with the number said digit by digit ("three, two, four, four"), the cost and the hours,
   then say that a free callback can also be booked. If a box already says "An advisor will call you
   back on …", mention that callback with its time.

## Book a callback
1. Open "Help". If a box already says "An advisor will call you back on …", stop and answer with the
   booked time (one callback at a time; cancel it first if she wants another one).
2. The reason, the time and the number come from the person. If the reason or the time is missing,
   call `ask_user` with one short question listing the choices the page offers
   (reasons: "My bill", "My plan", "A technical problem", "Other"; times: read them from the list).
3. In "Reason for your request", choose the reason. In "Callback time", choose the time.
4. In "Number to call back", keep the number shown. If the person wants another number, click the field
   and call `ask_user`: "Please type the number to call back yourself in the form, then say done."
5. Call `confirm_change` with `costs_money` = false and a summary such as:
   "ask an advisor to call you back tomorrow from 2 pm to 4 pm on 06 12 34 56 78, about your bill".
6. Only if the reply starts with "Approved": click "Ask to be called back".
   If refused: click nothing and answer that no callback was booked.
7. Check the green box "An advisor will call you back on …" and answer with it. If a red message
   appears, answer with that message.

## Cancel a booked callback
1. Open "Help" and find the box "An advisor will call you back on <number> <time> (reason: <reason>)".
   If there is none, answer that no callback is booked and stop.
2. Call `confirm_change` with `costs_money` = false and a summary such as:
   "cancel the callback planned tomorrow from 2 pm to 4 pm".
3. Only if the reply starts with "Approved": click "Cancel the callback". If refused: click nothing.
4. Check the green box "Your callback request has been cancelled." and answer with it.

## Never
- Never choose a reason or a time the person did not give.
- Never click "Ask to be called back" or "Cancel the callback" before `confirm_change` replied "Approved".
- Never click "Reset the demo" or "Log out".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
