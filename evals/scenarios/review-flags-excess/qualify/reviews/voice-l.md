LGTM except:

* R8: Z-A on ties, the reverse flag hits names too.
* R10: footer total != sum of lines (days*50).
* I'd cut the FineRule/registry layer, the rounding switch, and the cache. R7/R1 don't need them.

(retry = R11, csv = R9, both fine)
