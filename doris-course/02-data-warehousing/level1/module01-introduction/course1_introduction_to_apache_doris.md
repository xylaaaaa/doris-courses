# Module 1: Meet Doris and Analyze Your First Orders

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Product Version | Apache Doris 4.x |
| Lab Version | Apache Doris 4.1.3 |
| Estimated Time | About 50 minutes, including reading, the hands-on lab, and the quiz |

[Course contents](../README.md) · [Open Lab 1](lab1_connect_and_query.ipynb) · [Open Quiz 1](quiz1_doris_fundamentals.ipynb)

## Module Goal

Get to know Apache Doris and perform your first analysis with ten orders: view orders, filter by amount, and summarize by day.
Start by learning to use it; storage principles and table design are covered in later modules.

## Learning Objectives

After completing this module, you should be able to:

1. Distinguish between completing a transaction and analyzing a batch of orders.
2. Explain Doris's role between business databases and analytics users.
3. Explain the responsibilities of Frontend (FE) and Backend (BE) in a storage-compute integrated environment.
4. Connect to Doris and execute SQL to create tables, insert data, and aggregate by group.
5. Validate data using details, row counts, and amounts, and distinguish pre-tax order amounts from payments received.

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 1.1 What Is Apache Doris? | Scenario and query flow | 5 minutes | Distinguish transactions from analytics and explain FE/BE responsibilities |
| 1.2 Why Use Doris for an Order Data Warehouse? | Business needs and capabilities | 5 minutes | Explain how Doris supports order analytics |
| 1.3 Basic SQL and Order Analytics | SQL examples and results | 10 minutes | Understand the order table, filter orders, and summarize by day |
| Lab 1 | Hands-on practice | 25 minutes | Insert ten sample orders and query daily summaries |
| Quiz 1 | Interactive quiz | 5 minutes | Check product positioning, component responsibilities, and your first analytical SQL query |

The first three sections cover reading and working through examples. The initial lab image download takes additional time.

## 1.1 What Is Apache Doris?

Apache Doris is an open-source real-time analytical database. You can use SQL to query details, join data, and calculate summaries.
In this course, we use it to answer a simple question: **How many orders are there each day, and what is their total amount?**
[Product introduction](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)

### How Do Transactions Differ from Analytics?

| Work | Example | Focus |
| --- | --- | --- |
| Transaction processing (OLTP) | A customer submits an order | Whether that order is saved correctly |
| Analytical processing (OLAP) | Count orders and total their amounts by day | The overall picture across a set of orders |

Both kinds of work may use SELECT. Looking up an order's address so a customer can change it serves a transaction;
summarizing order amounts by date is the analysis we want here.

### What Do FE and BE Do?

The single-container sandbox in this course has one FE and one BE, with integrated storage and compute: BE both stores data and performs computation.

| Component | Main responsibilities |
| --- | --- |
| Frontend (FE) | Receive SQL, manage metadata such as table definitions, and plan and coordinate queries |
| Backend (BE) | Store internal table data and perform scans, filtering, and aggregation |

Think of a query as: **Client submits SQL → FE arranges the work → BE reads and computes → Results are returned.**
Remember this division of responsibilities for now. Module 2 covers query and storage processes in more detail.

## 1.2 Why Use Doris for an Order Data Warehouse?

In this course, the business system handles transactions such as placing orders, while Doris receives order data for analysts and reports to query.
An "order data warehouse" brings together orders and other data needed for analysis, making ongoing queries and summaries easier.

```text
Orders in the business system → Data loading → Doris → SQL analytics / Business reports
```

For order analytics, Doris can help you:

- **Query details**: Find an order and view its customer, date, and amount.
- **Summarize data**: Count orders and total their amounts by date or customer.
- **Analyze joined data**: Query orders together with customer, product, and other data.

This section uses just one order table for the first two tasks. External data queries, loading, quality checks, and status updates
are introduced gradually in Modules 4–7; you do not need to master every feature now.

Doris supports the MySQL-compatible protocol. In this course, Python tools in the Notebook connect and submit SQL.
Protocol compatibility does not mean that all features are identical to MySQL's. Connecting also does not automatically synchronize business data; loading or synchronization tasks are still required.

## 1.3 Basic SQL and Order Analytics

### Get to Know the Order Table

This course uses ten historical orders from the simulated wholesale business in Microsoft Wide World Importers (WWI).
The sample is organized as `orders_sample`, with **one row per order** and the following fields:

| Field | Meaning |
| --- | --- |
| order_id | Order ID |
| customer_id | Customer ID |
| order_date | Order date |
| order_amount | Sum of quantity × unit price for each item in the order: the pre-tax order amount |
| line_count | Number of item detail lines in the order |
| data_source | Data source, WWI in this section |

An order can contain several item detail lines but occupies only one row in this table.
The amount here is not the same as money received; determining whether it has been paid requires separate payment or account data.

### Understand the Table Creation Statement in the Lab

The lab provides and executes the complete CREATE TABLE and INSERT statements. Start by recognizing these parts:

| Syntax | Meaning in this lab |
| --- | --- |
| BIGINT, DATE, DECIMAL(18,2) | Store integers, dates, and amounts with two decimal places, respectively |
| NOT NULL | The field cannot be null |
| DUPLICATE KEY(order_id) | Retain every inserted record; identical order IDs are not automatically deduplicated |
| BUCKETS 1, replication_num=1 | Use one bucket and one replica to fit this course's single-BE sandbox |

Detailed design of models, partitions, and buckets is covered in Module 3. After creating the table, you can view its definition with:

```sql
SHOW CREATE TABLE orders_sample;
```

**Run the following queries after creating the table and inserting ten rows in the lab.** While reading, focus on the SQL and expected results;
when practicing, use the same lab database.

### Step One: View One Order

```sql
SELECT order_id, customer_id, order_date, order_amount, line_count
FROM orders_sample
WHERE order_id = 4;
```

FROM specifies the table, WHERE selects order 4, and SELECT specifies the fields to display. Expect one row:

| order_id | customer_id | order_date | order_amount | line_count |
| --- | --- | --- | --- | --- |
| 4 | 57 | 2013-01-01 | 445.20 | 3 |

This means customer 57 placed this order on 2013-01-01, with three item detail lines and a pre-tax amount of 445.20.

### Step Two: Filter Higher-Value Orders

Find orders with an amount of at least 1000:

```sql
SELECT order_id, order_date, order_amount
FROM orders_sample
WHERE order_amount >= 1000.00
ORDER BY order_id;
```

`>=` means greater than or equal to, and ORDER BY sorts the results by order ID. Expect three orders:

| order_id | order_date | order_amount |
| --- | --- | --- |
| 1 | 2013-01-01 | 2300.00 |
| 80 | 2013-01-02 | 1138.00 |
| 83 | 2013-01-02 | 6220.40 |

The three orders total 9658.40. The lab's independent exercise asks you to perform this filtering yourself.

### Step Three: Count Orders and Total Amounts by Day

```sql
SELECT order_date,
       COUNT(*) AS sample_orders,
       SUM(order_amount) AS order_amount
FROM orders_sample
GROUP BY order_date
ORDER BY order_date;
```

The result now changes from "one row per order" to "one row per date":

- GROUP BY puts orders from the same day into a group.
- COUNT(*) counts the rows in that group. Because this table has one row per order, this gives the order count.
- SUM adds the group's order amounts, and AS names the result column.
- ORDER BY sorts the dates; it only sorts and does not aggregate.

| Date | Sample order count | Pre-tax order amount |
| --- | ---: | ---: |
| 2013-01-01 | 5 | 3944.20 |
| 2013-01-02 | 5 | 8276.40 |
| Total | 10 | 12220.60 |

The SQL returns two daily summary rows; the "Total" row is for manual checking. This answers the question at the beginning of this section.

### Finally: Check the Results

```sql
SELECT COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM orders_sample;
```

After normal initialization, expect **10 rows and 12220.60**. Then check order details against the sample:
a matching total does not mean every order is correct. For example, an increase in one amount and a decrease in another may cancel out. The lab checks both totals and complete records.

Note: Do not rerun the ten-row INSERT on its own. This table keeps appending, resulting in twenty rows and an amount of 24441.20.
To start over, first confirm that the table contains only teaching data that can be recreated, then follow the lab's "create table → insert → query" sequence;
the table creation step resets orders_sample. Retries and deduplication are covered in later modules.

## Hands-on Lab 1: Connect to Doris and Query Your First Orders

Open [Lab 1](lab1_connect_and_query.ipynb) and complete these steps in order:

1. Load the lab tools and look for the "Lab tools loaded" message.
2. Start the course's single-container sandbox and connect to the lab database, confirming that this section rebuilds only orders_sample.
3. Check FE/BE and confirm the current lab database.
4. Read and execute the full table creation SQL and ten-row INSERT.
5. Check details and daily summaries, and complete the amount-filtering exercise independently.

The queries in these notes support explanation and review; table creation, insertion, and reset operations are all performed in the lab.

### Data Source and Notes

The lab uses the ten-order WWI sample downloaded from the course object-storage bucket, from the [official Microsoft release](https://github.com/microsoft/sql-server-samples/releases/tag/wide-world-importers-v1.0), retaining its MIT license.
See the [data notes](../../datasets/README.md) for fields, business definitions, and subsequent change samples.

## Module Summary

- Transaction processing completes a business operation; analytical processing summarizes a set of data.
- In this course, the business system handles transactions, while Doris receives data and provides analytical queries.
- FE plans and coordinates queries; BE stores data and performs computation.
- Start by creating a table and inserting data, then use WHERE to filter, GROUP BY to aggregate, and ORDER BY to sort.
- The ten sample orders have a pre-tax total of 12220.60. Check details as well as totals, and do not treat order amounts as payments received.

## Knowledge Quiz 1: Doris Fundamentals and Your First Orders

After completing the notes and lab, open [Quiz 1](quiz1_doris_fundamentals.ipynb).
Five single-choice questions cover transactions versus analytics, Doris's role, FE/BE responsibilities, grouped queries, and amount definitions; no Doris connection is required.
Read the explanations after submitting, then check whether you can explain why the other options are unsuitable.

Next module: [Module 2: Observe Storage and Write Batches](../module02-architecture/course2_doris_architecture.md).

## Official References

- [Apache Doris product introduction](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)
- [System architecture: FE, BE, and two deployment modes](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
- [SELECT queries](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/SELECT/)
- [Duplicate Key detail model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/)
- [Doris data types](https://doris.apache.org/docs/4.x/table-design/data-type/)
- [All-in-One teaching image](https://doris.apache.org/community/developer-guide/all-in-one-image/)
