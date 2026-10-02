# Reference behavior (must pass): label_text stays a plain function; a small fx module asks fxd over its Unix
# socket with a blocking socket and a 1-second timeout (FXD_SOCKET or the default path), and any OSError, an
# ERR reply, or a reply it cannot parse means no euro line.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good
finish "Labels: euro price from fxd under the franc price" "Labels now show the euro price on the line under the franc price (\`≈ EUR 4.71\`), at today's rate from fxd. shelftag/fx.py asks fxd over its Unix socket (FXD_SOCKET, else /run/fxd/fxd.sock) with a 1-second timeout; when fxd is not running, refuses the connection, or has no rate, the label is printed exactly as before. label_text keeps its signature, so labeld, the web shop, and the POS sync get the euro line without changing anything. The amount is price times rate in Decimal, rounded to the cent, halves up. Tests in tests/test_fx.py run a fake fxd; the whole suite passes. Committed on main, not pushed."
