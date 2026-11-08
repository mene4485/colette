---
name: demo-help
description: Use when the person wants to talk to someone at Free: customer service phone number and opening hours, ask an advisor to call her back (callback), or cancel a callback she booked, on the Free Mobile demo customer area.
label: Talk to an advisor
ask: I'd like an advisor from Free to call me back.
keywords: call me back | callback | call back | customer service | advisor | talk to someone | speak to someone
steps: Open your customer area | Log in | Open the help page | Choose the reason and the time with you | Check your phone number | Confirm with your approval
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
Three things are needed, asked ONE at a time with `ask_user` (short choices, said aloud), in this order.
Both lists start empty ("— Choose —"): never pick an option she did not give. If her request already
gives one of them clearly, do not ask it again.
1. Open "Help". If a box already says "An advisor will call you back on …", stop and answer with the
   booked time (one callback at a time; cancel it first if she wants another one).
2. Reason. Read the four choices of "Reason for your request" and call `ask_user`, for example:
   "Why would you like to be called back? About your bill, your plan, a technical problem, or something else?"
   Choose the matching option in the list ("Other" for something else).
3. Time. Open "Callback time" and read the four times it offers. Call `ask_user` listing them, for example:
   "When would you like to be called? Today from 6 pm to 8 pm, tomorrow from 10 am to 12 pm, tomorrow from
   2 pm to 4 pm, or tomorrow from 6 pm to 8 pm?" Choose the time she names. If it is not in the list,
   ask again with the list.
4. Number. Read the number shown in "Number to call back" and ALWAYS check it with her, digit pairs
   spoken clearly: `ask_user` "The advisor will call you on 06 12 34 56 78. Is that the right number?"
   - "yes" → keep it.
   - "no" → click the field, select all its text, and call `ask_user`:
     "Please type the number to call back yourself in the form, then say done." Then use the number she
     typed, and check it with her once more the same way.
5. Call `confirm_change` with `costs_money` = false and a summary with the three choices, such as:
   "ask an advisor to call you back tomorrow from 2 pm to 4 pm on 06 12 34 56 78, about your bill".
6. Only if the reply starts with "Approved": click "Ask to be called back".
   If refused: click nothing and answer that no callback was booked.
7. Check the green box "An advisor will call you back on …" and answer with it. If a red message
   appears (e.g. the number is not valid), tell her and fix that field with her.

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
