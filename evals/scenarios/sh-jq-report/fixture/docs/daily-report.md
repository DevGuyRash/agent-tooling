# The daily edge report

`scripts/daily-report.sh ACCESS_LOG` prints these sections, each after a blank line except the first. Requests are the log's readable lines (`docs/log-format.md`).

## Summary

    Edge report: access-2025-09-30.jsonl
    requests: 12408 (3 unreadable lines skipped)

The log's file name, the number of requests, and the number of non-blank lines that are not readable requests.

## Status classes

    Status classes
    2xx   11902   95.9%
    4xx     478    3.9%
    5xx      28    0.2%

Requests per status class (status divided by 100, rounded down), lowest class first, classes with no requests left out; the percentage of all requests with one decimal (printf's `%.1f`).

## Top routes

    Top routes
       4211  GET /v1/invoices/{id}
       2980  POST /v1/payments

The ten busiest method and route pairs, busiest first; ties in byte order of method and route.

## Top tenants

    Top tenants
       3102  acme-co              enterprise
        877  initech              pro

The five tenants with the most requests and their plans (`config/tenants.tsv`; a tenant not listed there is on the plan of the `*` row); ties in byte order of the tenant id. Anonymous requests are left out.

## Tenants over budget

Not in the report yet. Ines wrote this up with support in September: they want to see each morning which tenants had a bad day.

A tenant is over budget when, in the log:

- 1% or more of its requests got a 5xx status (500 to 599), or
- its p95 latency is above its plan's budget.

p95 is nearest-rank: sort the tenant's `ms` values from lowest to highest and take the one at position ⌈0.95 × n⌉, counting from 1, where n is the tenant's number of requests. Plans and budgets are in `config/tenants.tsv`; a tenant not listed there is on the plan of the `*` row. Anonymous requests are left out.

The section comes last, after Top tenants:

    Tenants over budget
    tenant               plan        requests    5xx   rate     p95  budget
    northwind-labs       standard        2210     31   1.4%     612     800
    acme-co              enterprise      3102     12   0.4%     341     300

One line per tenant over budget, most errors first: by 5xx rate, highest first (comparing the rates themselves, not the rounded figures); then by p95, highest first; then by tenant id in byte order. The header is printed with

    printf '%-20s %-10s %9s %6s %6s %7s %7s\n' tenant plan requests 5xx rate p95 budget

and each line with

    printf '%-20s %-10s %9d %6d %5.1f%% %7d %7d\n' TENANT PLAN REQUESTS ERRORS RATE P95 BUDGET

where RATE is 100 × ERRORS ÷ REQUESTS. When no tenant is over budget, the heading is followed by the single line `none`.
