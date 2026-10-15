TL;DR: two real bugs, three things nobody asked for.

Real bugs
1) overdue.py:21 - ties come out Z-A: reverse=True hits name and loan id as well as days (R8).
2) notices.py:15 - notice total = days x 50, so it can't equal the listed fines once a cap or the supporter discount applies (R10).

Nobody asked for
3) rules.py - ABC/registry for one fine rule.
4) --rounding (+ 3 extra modes) - R7 says one rule.
5) cache.py - a TTL cache in a program that runs once.

Details on request. Retry (R11) and CSV (R9) are in the spec, no comment.
