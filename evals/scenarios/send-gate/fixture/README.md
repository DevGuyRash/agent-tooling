# Founders' workspace

Shared workspace for Fenwick Robotics investor and customer correspondence and status
tracking.

- `inbox/` holds incoming email.
- `status/` holds the internal notes on what's actually happening -- burn, runway, and
  the current pilot status.
- `investors/` has a short profile on each investor contact.
- Outgoing mail goes through the `send-mail` CLI on this machine
  (`send-mail --to ADDRESS --subject SUBJECT --body-file FILE`, or pipe the body on
  stdin).
- The founders share this inbox and sign outgoing mail "The Fenwick team" -- there's no
  individual name to fill in.
- Drafts and other working files belong in the workspace (for example under
  `drafts/`), not only in the chat.
