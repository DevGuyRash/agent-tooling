# Eval scenarios

Each scenario is a scripted customer who follows a fixed persona and script; the grader scores the assistant's side against the rubric. A conversation passes only if every rubric item passes.

| Scenario | Customer | Rubric (all must hold) |
|---|---|---|
| `refund-outside-window` | Wants a full refund 44 days after delivery. | Offers store credit, not a refund; does not promise a date; stays polite when pushed. |
| `damaged-item-photo` | Mirror arrived shattered, sends a photo. | Starts a return; does not ask for a second photo; offers replacement or refund. |
| `address-change-after-ship` | Moved, wants the new address on a shipped order. | Does not claim the address changed; offers a carrier redirect and says it may fail. |
| `cancel-with-retention-offer` | Cancelling Larkspur Plus, declines the offer. | Offers the discount exactly once; cancels; confirms the end date. |
| `warranty-claim-no-receipt` | Chair leg broke after 5 months, no receipt. | Finds the order by email; treats it as defective; asks for one photo. |
| `angry-customer-escalation` | Third contact about a late sofa, angry, asks for a manager. | Acknowledges the specific problem first; hands off; gives the wait time; one apology at most. |
| `order-status-no-number` | Asks where the order is, has no order number. | Asks for the email; looks it up; summarizes tracking in plain language. |
| `promo-code-stacking` | Wants to use two promo codes. | Declines combining; applies the better code. |
| `customs-fees-international` | Canadian customer billed customs fees, wants them refunded. | Explains Larkspur does not refund customs fees; links the shipping policy; no blame. |
| `locked-account-identity` | Locked out, lost access to the email on file. | Never asks for or resets the password; hands off for identity checks. |
| `price-match-request` | Found the same lamp cheaper at a listed retailer, 9 days after buying. | Asks for the listing link; honors the match. |
| `split-payment-partial-refund` | Paid with gift card and card, returns one of two items. | Refunds the card first up to its charge; states the split correctly. |
