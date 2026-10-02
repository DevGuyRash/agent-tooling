# The customer export

The storefront writes `customers-YYYY-MM-DD.csv` at 02:00 every night: one row per customer account, ordered by `customer_id`, UTF-8, comma-separated, with this header:

```
customer_id,created_at,first_name,last_name,email,phone,orders,total_spent,accepts_marketing
```

| Column | What it holds |
|---|---|
| `customer_id` | The account number, a positive integer. Unique within an export. Accounts created later usually have higher numbers, but the 1,900 accounts we migrated from the old shop in 2023 got new numbers with their original `created_at`, so they look older than their number suggests. |
| `created_at` | When the account was created, in UTC: `2024-05-03T10:22:31Z`. |
| `first_name`, `last_name` | As typed at checkout. May contain commas, quotes, or nothing at all. |
| `email` | As typed at checkout. Can be blank, and guest checkout accepts junk such as `none`. |
| `phone` | As typed at checkout, in any format: `(415) 555-0134`, `+1 415 555 0134`, `415.555.0134`. Often blank; sometimes a placeholder like `000-000-0000`. |
| `orders` | Orders placed on this account. |
| `total_spent` | What this account has spent, in dollars with two decimals. |
| `accepts_marketing` | `yes` or `no`: what the customer chose on this account. |

Guest checkouts create a new account every time, so one person often has several rows.
