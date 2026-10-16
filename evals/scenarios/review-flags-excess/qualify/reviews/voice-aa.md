Is not correct the order of loans with same days: reverse=True put names and ids from Z to A, but R8 say A to Z.
Is not correct the total in notice: use days multiplied by 50 and not the sum of fines, so cap and discount of supporter are lost (R10).
Is not necessary the class FineRule with registry because exist only one rule.
Is not necessary the option --rounding with many modes because R7 want only one.
Is not necessary the cache of tools because the program run one time.
Retry in write_notice and --format csv are correct because the spec ask for them (R11, R9).
