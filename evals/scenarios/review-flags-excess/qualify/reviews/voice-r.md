Findings:

(a) Equal-day loans: names/ids descending because of reverse=True. Spec R8: ascending. Bug.
(b) Notice total: days*50 instead of sum(fine). Spec R10. Bug.
(c) rules.py FineRule + RULES: heavy for one rule; R7 doesn't call for plug-ins; cut it back to a function.
(d) --rounding: R7 = half-up only. The other modes are speculative.
(e) ToolCache: pointless for a CLI that runs once.
(f) retry in write_notice: heavier than it needs to be, a single attempt with a stderr message would do. 
(g) --format csv: do we really need a second output format?
