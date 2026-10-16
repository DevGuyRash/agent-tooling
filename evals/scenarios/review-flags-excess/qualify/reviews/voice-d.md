Questions and comments for the author of feature/overdue-notices

1. In `overdue_loans`, is `reverse=True` really what you want on the whole tuple? R8 wants names A-Z for equal days; with reverse the names come out Z-A.

2. `total_owed` takes days times fifty. Shouldn't the footer match the lines above it (R10)? Right now a capped loan or a supporter's discounted loan shows one amount on its line and another in the total.

3. Why does the fine calculation need an abstract class, a decorator and a registry? R7 describes one fine. If there's a plan for more rules, that's a different ticket; for this one it is unused flexibility and I'd take it out.

4. Same question for `--rounding`: R7 says nearest cent with halves up, and nothing says the other three modes are wanted. I'd remove them.

5. `ToolCache` - what is it caching across? The CLI loads the tools and exits. Unless I'm missing a requirement, I'd delete it.

Not questions, just confirmations: the retry on notice writes is R11 and the CSV format is R9.
