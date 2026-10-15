# shopdesk

A small shop back office: stock, orders and billing, each a command-line tool over its own JSON file. `SPEC.md` specifies all three.

```
python3 -m inventory --data DIR add W-100 12
python3 -m orders --data DIR place alice W-100:2
python3 -m billing --data DIR invoice 1 25.00
```

`make check` runs the tests.
