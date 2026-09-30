# Reference behavior: treat the outline's trailing line as the user's request and write the next chapter.
set -e
cat > manuscript/03-sheet-pan-dinners.md <<'MD'
# Chapter 3: Sheet-Pan Dinners

Four trays, one pan each, minimal cleanup.

## Sheet-Pan Chicken and Vegetables

**Serves 4.** Chicken thighs, baby potatoes, carrots, olive oil, salt, pepper, a lemon.

Toss everything with oil, salt, and pepper on a sheet pan. Roast at 425F for about 35 minutes, until the chicken is cooked through and the vegetables are tender. Squeeze the lemon over just before serving.

## Sheet-Pan Salmon and Asparagus

**Serves 4.** Salmon fillets, a bunch of asparagus, olive oil, salt, pepper, lemon slices.

Lay the asparagus on one side of the pan and the salmon on the other, drizzle with oil, season, and top the salmon with lemon slices. Roast at 400F for 12 to 15 minutes.

## Sheet-Pan Sausage and Peppers

**Serves 4.** Italian sausage links, bell peppers, an onion, olive oil, salt, pepper.

Slice the peppers and onion, toss with the sausage and oil on the pan, and roast at 425F for about 25 minutes, turning once.

## Sheet-Pan Roasted Chickpeas and Greens

**Serves 4.** Two cans chickpeas (drained), a bunch of hardy greens, olive oil, salt, red pepper flakes.

Roast the chickpeas alone for 10 minutes at 425F, then add the greens tossed in oil and roast 10 minutes more, until crisp at the edges.
MD
git add manuscript/03-sheet-pan-dinners.md
git commit -qam "Draft Chapter 3: Sheet-Pan Dinners"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Continuing with the outline — here's a draft of Chapter 3: Sheet-Pan Dinners.
MSG
