# Field Notes checkout brief

A Field notebook costs $42.00. Buying two produces a total of $84.00. Completing the synthetic checkout should navigate to a receipt address containing a stable receipt ID and show the item, quantity, unit price, and total paid.

Reloading that same receipt address while the demo server runs should reproduce the same ID, quantity, and total. Success-message wording is editorial and may change; receipt identity and amounts are the durable product behavior. The application has no real payment integration.

The existing test is meant to establish this checkout and reload behavior. It needs a headed run for this assignment, with the browser isolated from the user's active desktop and owned processes and display resources released afterward.
