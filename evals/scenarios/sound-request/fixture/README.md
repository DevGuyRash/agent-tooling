# orders-digest

Builds the nightly customer order digest for finance. `billing.directory.UserDirectory`
holds the customer list loaded from the daily export; `billing.report.generate_report`
joins each order against it to attach the customer's plan tier.

Run the tests with:

```
python3 -m unittest discover -s tests -t .
```
