Two blocking points and some trimming.

Blocking: the tie order is backwards for equal days (names and loan ids descend because of `reverse=True`; R8 says ascending), and a notice's total ignores the cap and the supporter discount because it is computed from days at 50 cents rather than from the fines (R10).

Trimming, if you want the branch to stay close to R6-R11: the abstract rule class and registry could be a function; the rounding switch could go because R7 has one rule; the tool cache could go because the command runs once.
