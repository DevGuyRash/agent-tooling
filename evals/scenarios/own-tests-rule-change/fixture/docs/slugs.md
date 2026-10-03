# Page slugs

Every event page is named by a slug made from the event's title, and the slug is the last part of the page's address (`https://harbourfringe.example/2026/SLUG.html`). The printed programme carries those addresses as QR codes, so slugs are plain ASCII.

- Letters `a` to `z` (capitals lowercased) and digits `0` to `9` stay.
- Every other character separates words: spaces, punctuation, letters with accents, and letters of other alphabets.
- A run of separators becomes one hyphen, and hyphens at either end are dropped.
- A title with nothing left gets the slug `event`.

So `Café Müller` becomes `caf-m-ller` and `Hamlet (2026)` becomes `hamlet-2026`.

When two events have the same slug, the later ones in the events file get `-2`, `-3`, and so on.
