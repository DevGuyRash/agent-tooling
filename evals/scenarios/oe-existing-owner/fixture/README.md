# clubroll

Membership for a small club.

- `clubroll/signup.py`: `sign_up(store, address, name)`, how someone joins.
- `clubroll/validation.py`: the club's input rules; `clubroll/data/` holds the lists they read.
- `clubroll/store.py`: the records (members and invites), in memory here.

Invites are meant to work like this: a member invites a friend by address, the invite is recorded in the store as pending, and the mailer (a separate service) sends every pending invite. The mailer expects addresses in the form the store keeps them in.

Run `make check` before handing work back: it runs the tests and byte-compiles the package. Python 3.10 or newer, standard library only.
