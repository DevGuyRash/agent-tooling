# Eval scenarios

Each scenario is one ticket with the expected queue and priority. A reply passes when it is valid JSON with exactly `queue`, `priority`, `needs_human`, and `summary`, and the queue and priority match.

| Scenario | Ticket (abridged) | Expected |
|---|---|---|
| `password-reset-loop` | Reset link keeps sending me back to the login page; can't get into email. | identity, P1 |
| `vpn-drops-on-wifi` | VPN disconnects every few minutes on home Wi-Fi, fine on hotspot. | network, P2 |
| `new-hire-laptop-request` | New analyst starts Monday, needs a laptop and accounts. | identity, P3 |
| `printer-queue-stuck` | Second-floor printer shows jobs queued but prints nothing. | endpoint, P3 |
| `shared-mailbox-access` | Please give my new team lead access to the dispatch mailbox. | identity, P3 |
| `mfa-phone-replaced` | Got a new phone, authenticator codes gone, locked out. | identity, P1 |
| `software-license-renewal` | Our CAD licenses expire Friday, renewal quote is $4,800. | procurement, P2 |
| `phishing-report` | Got an email "from payroll" asking me to confirm bank details, didn't click. | security, P1 |
| `badge-access-after-hours` | My badge stops working after 7pm, I'm on the night shift from next week. | facilities-av, P3 |
| `onboarding-account-batch` | Six seasonal warehouse staff start tomorrow, need logins for the scanner app. | identity, P2 |
| `data-restore-request` | Accidentally deleted the Q3 shipment folder this morning, need it back. | endpoint, P2 |
| `conference-room-display` | Boardroom screen won't show laptops over HDMI, client meeting at 2pm today. | facilities-av, P2 |
