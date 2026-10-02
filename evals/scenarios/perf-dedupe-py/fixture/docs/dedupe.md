# One row per person

The newsletter service bills us per contact and treats every row of the export as a separate person, so the export has to be collapsed to one row per actual person before the nightly upload. This is how I've been doing it in a spreadsheet, and how `shopcrm dedupe` should do it. — Priya

```
python3 -m shopcrm dedupe EXPORT.csv > people.csv
```

The input is an export as described in [export-format.md](export-format.md) that passes `shopcrm validate`. The output, on standard output, is CSV with the export's header plus one more column, `merged_ids`, at the end.

## Who is the same person

Two rows are the same person when they have the same email address or the same phone number. Compare them the way `shopcrm lookup` does: case and surrounding spaces don't matter in emails, only the digits of a phone number count (a leading US country code 1 is dropped), and values that aren't real addresses or numbers (`none`, `n/a`, `000-000-0000`, numbers that aren't ten digits) never match anybody.

It carries over: if row A and row B are the same person and row B and row C are the same person, then A, B, and C are all one person, even when A and C have nothing in common. The rows that tie a person together can be anywhere in the export.

## What goes in a person's row

Order a person's accounts oldest first: by `created_at`, and by the lower `customer_id` when two were created in the same second.

| Column | Value |
|---|---|
| `customer_id`, `created_at`, `first_name`, `last_name` | From the oldest account. |
| `email`, `phone` | The first one, going from the oldest account to the newest, that is a real address or number by the rules above, exactly as written there. Blank if no account has one. |
| `orders` | The total over all the person's accounts. |
| `total_spent` | The total over all the person's accounts, with two decimals. |
| `accepts_marketing` | From the newest account: the latest choice the person made. |
| `merged_ids` | The `customer_id`s of the person's other accounts, oldest first, separated by single spaces. Blank for a person with one account. |

People come out ordered by their oldest account, the same way: by `created_at`, then `customer_id`.

## Example

```
customer_id,created_at,first_name,last_name,email,phone,orders,total_spent,accepts_marketing
1001,2023-02-11T09:15:02Z,Dana,Whitfield,dana.w@example.com,,2,64.00,no
1002,2023-03-02T17:40:55Z,Omar,Haddad,omar@example.net,(503) 555-0187,1,18.50,yes
1003,2023-05-19T12:01:13Z,Dana,Whitfield,,503-555-0142,1,22.00,no
1004,2023-06-07T08:22:40Z,D,Whitfield, Dana.W@Example.com ,+1 503 555 0142,3,95.25,yes
1005,2023-07-21T19:05:09Z,Omar,Haddad,none,000-000-0000,1,12.00,no
1006,2021-11-30T10:00:00Z,Dana,Whitfield,n/a,5035550142,4,140.00,no
```

Row 1004 has Dana's email from 1001 and the phone number from 1003, and 1006 (migrated from the old shop, so it is the oldest despite its number) has that phone number too: all four are Dana. Her row takes the email from 1001, since 1006's `n/a` is not an address. Row 1005 shares nothing real with 1002, so Omar stays two people, and 1005's row has neither an email nor a phone.

```
customer_id,created_at,first_name,last_name,email,phone,orders,total_spent,accepts_marketing,merged_ids
1006,2021-11-30T10:00:00Z,Dana,Whitfield,dana.w@example.com,5035550142,10,321.25,yes,1001 1003 1004
1002,2023-03-02T17:40:55Z,Omar,Haddad,omar@example.net,(503) 555-0187,1,18.50,yes,
1005,2023-07-21T19:05:09Z,Omar,Haddad,,,1,12.00,no,
```
