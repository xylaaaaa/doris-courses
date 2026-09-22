# Further reading: WWI invoices and account receipts (optional)

[Return to Module 5](course5_batch_and_streaming_ingestion.md)

First complete the ten historical table loads in Lab 5. This page only queries existing tables and does not modify data;
it helps explain different amount definitions and is not a required step in the main batch-loading path.

## Do not mix three kinds of amounts

| Data | What it represents | How this course uses it |
| --- | --- | --- |
| Orders and product lines | Ordered quantities and unit prices | Sum Quantity × UnitPrice for pre-tax order amounts |
| Invoices and invoice lines | Invoicing records | Interpret invoice fields without treating them as received payments |
| Customer account transactions | Account amounts recorded by transaction type | Retain original ledger signs without forcing per-order allocation |

## Inspect account records by transaction type

```sql
SELECT t.TransactionTypeName, COUNT(*) AS rows_count,
       SUM(c.TransactionAmount) AS ledger_amount,
       SUM(CASE WHEN c.InvoiceID IS NULL THEN 1 ELSE 0 END) AS no_invoice_link
FROM wwi_customer_transactions c
JOIN wwi_transaction_types t ON c.TransactionTypeID=t.TransactionTypeID
GROUP BY t.TransactionTypeName ORDER BY t.TransactionTypeName;
```

Here CASE assigns 1 when there is no linked invoice and 0 otherwise; SUM then counts these records.
Observe the signs of receipt types and no_invoice_link: negative account receipts in this sample cannot be treated directly as order refunds,
and amounts cannot justify forced allocation when per-order payment links are absent. Module 6 further practices classification with CASE.

```sql
SELECT SUM(TransactionAmount) AS ledger_balance,
       SUM(OutstandingBalance) AS outstanding_balance
FROM wwi_customer_transactions;
SELECT COUNT(*) AS delivered_invoices
FROM wwi_invoices WHERE ConfirmedDeliveryTime IS NOT NULL;
```

In the course's fixed WWI package, both columns of the first query are 267011.44, and the second query returns 70426.
These are verification values for this sample, not accounting identities true for all companies; account balances and delivered-invoice counts are not order payment amounts.
Payments and refunds for simulated new orders use separate business transactions in Module 7, distinct from this WWI history.

See the [Course data guide](../../datasets/README.md) for data sources, the MIT license, and field descriptions.
