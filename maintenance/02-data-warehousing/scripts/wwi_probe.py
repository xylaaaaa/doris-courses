"""Author-only WWI feasibility probe. No upload, no resets, no course data changes.

Use an isolated SQL Server container and a fresh Doris database. Dependencies:
pymssql, pymysql, pyarrow, requests. Generated files belong outside the repository.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import pyarrow as pa
import pyarrow.parquet as pq
import pymssql
import pymysql
import requests


TABLES = {
    "orders": ("Sales.Orders", "OrderID CustomerID SalespersonPersonID BackorderOrderID OrderDate ExpectedDeliveryDate CustomerPurchaseOrderNumber IsUndersupplyBackordered PickingCompletedWhen LastEditedWhen"),
    "order_lines": ("Sales.OrderLines", "OrderLineID OrderID StockItemID Description Quantity UnitPrice TaxRate PickedQuantity PickingCompletedWhen LastEditedWhen"),
    "customers": ("Sales.Customers", "CustomerID CustomerName BillToCustomerID CustomerCategoryID BuyingGroupID DeliveryMethodID DeliveryCityID CreditLimit AccountOpenedDate StandardDiscountPercentage IsOnCreditHold PaymentDays"),
    "products": ("Warehouse.StockItems", "StockItemID StockItemName SupplierID ColorID Brand Size LeadTimeDays QuantityPerOuter IsChillerStock TaxRate UnitPrice RecommendedRetailPrice TypicalWeightPerUnit"),
    "invoices": ("Sales.Invoices", "InvoiceID CustomerID BillToCustomerID OrderID DeliveryMethodID InvoiceDate IsCreditNote CreditNoteReason TotalDryItems TotalChillerItems DeliveryRun RunPosition ReturnedDeliveryData ConfirmedDeliveryTime ConfirmedReceivedBy LastEditedWhen"),
    "invoice_lines": ("Sales.InvoiceLines", "InvoiceLineID InvoiceID StockItemID Description Quantity UnitPrice TaxRate TaxAmount LineProfit ExtendedPrice LastEditedWhen"),
    "customer_transactions": ("Sales.CustomerTransactions", "CustomerTransactionID CustomerID TransactionTypeID InvoiceID PaymentMethodID TransactionDate AmountExcludingTax TaxAmount TransactionAmount OutstandingBalance FinalizationDate IsFinalized LastEditedWhen"),
    "payment_methods": ("Application.PaymentMethods", "PaymentMethodID PaymentMethodName"),
    "transaction_types": ("Application.TransactionTypes", "TransactionTypeID TransactionTypeName"),
    "delivery_methods": ("Application.DeliveryMethods", "DeliveryMethodID DeliveryMethodName"),
}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def require(condition, detail):
    """Keep acceptance and scope checks enabled even under python -O."""
    if not condition:
        raise ValueError(detail)


def source_connection(container, database="WideWorldImporters"):
    # Read only the credential of the dedicated container specified by the author.
    metadata = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
    env = dict(item.split("=", 1) for item in metadata["Config"]["Env"])
    binding = metadata["NetworkSettings"]["Ports"]["1433/tcp"][0]
    require(binding["HostIp"] == "127.0.0.1", "Expected a loopback-only test container")
    return pymssql.connect("127.0.0.1", "sa", env["MSSQL_SA_PASSWORD"],
                           database=database, port=binding["HostPort"],
                           autocommit=True, login_timeout=10, timeout=300)


def query(connection, sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def restore(args):
    subprocess.run(["docker", "cp", str(args.artifacts / "wwi.bak"),
                    f"{args.container}:/tmp/wwi.bak"], check=True)
    with source_connection(args.container, "master") as connection:
        require(query(connection, "SELECT DB_ID('WideWorldImporters')")[0][0] is None,
                "Source database already exists; refusing to overwrite it")
        with connection.cursor() as cursor:
            cursor.execute("""RESTORE DATABASE WideWorldImporters FROM DISK='/tmp/wwi.bak'
                WITH MOVE 'WWI_Primary' TO '/var/opt/mssql/data/WWI.mdf',
                MOVE 'WWI_UserData' TO '/var/opt/mssql/data/WWI_userdata.ndf',
                MOVE 'WWI_Log' TO '/var/opt/mssql/data/WWI.ldf',
                MOVE 'WWI_InMemory_Data_1' TO '/var/opt/mssql/data/WWI_memory'""")
            while cursor.nextset():
                pass
    print("RESTORED", flush=True)


def mapped_type(sqltype, precision, scale):
    if sqltype in ("int", "smallint", "tinyint", "bigint"):
        return pa.int64(), "BIGINT"
    if sqltype == "bit":
        return pa.bool_(), "BOOLEAN"
    if sqltype in ("decimal", "numeric"):
        return pa.decimal128(precision, scale), f"DECIMAL({precision},{scale})"
    if sqltype == "date":
        return pa.date32(), "DATE"
    if sqltype in ("datetime", "datetime2"):
        return pa.timestamp("us"), "DATETIME(6)"
    if sqltype in ("nvarchar", "varchar", "nchar", "char"):
        return pa.string(), "STRING"
    raise ValueError(f"Unmapped source type: {sqltype}")


def export(args):
    manifest = {}
    with source_connection(args.container) as connection:
        for target, (source, names) in TABLES.items():
            metadata = {row[0]: row[1:] for row in query(connection, f"""
                SELECT c.name,t.name,c.precision,c.scale,c.is_nullable
                FROM sys.columns c JOIN sys.types t ON c.user_type_id=t.user_type_id
                WHERE c.object_id=OBJECT_ID('{source}')""")}
            fields, expressions, ddl = [], [], []
            for name in names.split():
                sqltype, precision, scale, nullable = metadata[name]
                arrow, doris = mapped_type(sqltype, precision, scale)
                fields.append(pa.field(name, arrow, nullable=bool(nullable)))
                expression = f"[{name}]"
                if sqltype in ("datetime", "datetime2"):
                    # Explicit microsecond truncation, including .9999999 sentinel dates.
                    expression = f"CAST(LEFT(CONVERT(varchar(27),[{name}],126),26) AS datetime2(6))"
                expressions.append(f"{expression} AS [{name}]")
                ddl.append(f"`{name}` {doris}" + (" NULL" if nullable else " NOT NULL"))
            primary = names.split()[0]
            select = f"SELECT {','.join(expressions)} FROM {source} ORDER BY [{primary}]"
            path = args.artifacts / f"{target}.parquet"
            count = 0
            with connection.cursor() as cursor, pq.ParquetWriter(path, pa.schema(fields), compression="snappy") as writer:
                cursor.execute(select)
                while True:
                    rows = cursor.fetchmany(10000)
                    if not rows:
                        break
                    arrays = [pa.array(values, type=field.type) for values, field in zip(zip(*rows), fields)]
                    writer.write_table(pa.Table.from_arrays(arrays, schema=pa.schema(fields)))
                    count += len(rows)
            create = (f"CREATE TABLE `{target}` ({','.join(ddl)}) DUPLICATE KEY(`{primary}`) "
                      f"DISTRIBUTED BY HASH(`{primary}`) BUCKETS 2 PROPERTIES ('replication_num'='1')")
            with path.open("rb") as payload:
                checksum = hashlib.file_digest(payload, "sha256").hexdigest()
            manifest[target] = dict(source=source, columns=names.split(), primary=primary,
                                    select=select, ddl=create, rows=count,
                                    bytes=path.stat().st_size, sha256=checksum)
            print("EXPORTED", target, count, path.stat().st_size, flush=True)
        manifest["_source_version"] = query(connection, "SELECT @@VERSION")[0][0]
    save(args.artifacts / "manifest.json", manifest)


def canonical(row):
    # Both drivers must hash decimals/dates/text identically; normalize bool to int.
    return json.dumps([str(int(v)) if isinstance(v, bool) else None if v is None else str(v)
                       for v in row], ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def row_digest(connection, select):
    digest = hashlib.sha256()
    count = 0
    with connection.cursor() as cursor:
        cursor.execute(select)
        while True:
            rows = cursor.fetchmany(10000)
            if not rows:
                break
            for row in rows:
                digest.update(canonical(row))
                count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def load(args):
    manifest = json.loads((args.artifacts / "manifest.json").read_text())
    with pymysql.connect(host="127.0.0.1", port=args.doris_port, user="root",
                         password=os.environ.get("DW_PASSWORD", ""), autocommit=True,
                         read_timeout=300) as connection, source_connection(args.container) as source:
        # Intentionally fails on an existing database: no destructive reset or append.
        query(connection, f"CREATE DATABASE `{args.database}`")
        query(connection, f"USE `{args.database}`")
        result = {"database": args.database, "backend": query(connection, "SHOW BACKENDS"), "tables": {}}
        for target, table in manifest.items():
            if target.startswith("_"):
                continue
            query(connection, table["ddl"])
            with (args.artifacts / f"{target}.parquet").open("rb") as payload:
                response = requests.put(f"http://127.0.0.1:{args.be_http}/api/{args.database}/{target}/_stream_load",
                    auth=("root", os.environ.get("DW_PASSWORD", "")), data=payload,
                    headers={"format": "parquet", "label": f"wwi_{target}_{uuid.uuid4().hex}",
                             "strict_mode": "true", "max_filter_ratio": "0", "timeout": "300"},
                    allow_redirects=False, timeout=330)
            response.raise_for_status()
            status = response.json()
            require(status["Status"] == "Success", status)
            require(status["NumberLoadedRows"] == table["rows"], status)
            require(status["NumberFilteredRows"] == 0, status)
            columns = ",".join(f"`{name}`" for name in table["columns"])
            actual = row_digest(connection, f"SELECT {columns} FROM `{target}` ORDER BY `{table['primary']}`")
            expected = row_digest(source, table["select"])
            result["tables"][target] = dict(load=status, expected=expected, actual=actual)
            save(args.artifacts / "load-results.json", result)
            require(actual == expected, (target, actual, expected))
            print("VERIFIED", target, actual["rows"], "all-column digest matches", flush=True)


CHECKS = {
    "order_dates": "SELECT MIN(OrderDate),MAX(OrderDate),COUNT(*) FROM orders",
    "order_line_amount": "SELECT SUM(Quantity*UnitPrice),SUM(Quantity) FROM order_lines",
    "invoice_amount": "SELECT SUM(ExtendedPrice),SUM(TaxAmount),SUM(LineProfit) FROM invoice_lines",
    "orphan_order_lines": "SELECT COUNT(*) FROM order_lines l LEFT JOIN orders o ON l.OrderID=o.OrderID WHERE o.OrderID IS NULL",
    "orphan_order_customers": "SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.CustomerID=c.CustomerID WHERE c.CustomerID IS NULL",
    "orphan_line_products": "SELECT COUNT(*) FROM order_lines l LEFT JOIN products p ON l.StockItemID=p.StockItemID WHERE p.StockItemID IS NULL",
    "orphan_invoice_lines": "SELECT COUNT(*) FROM invoice_lines l LEFT JOIN invoices i ON l.InvoiceID=i.InvoiceID WHERE i.InvoiceID IS NULL",
    "orphan_invoice_orders": "SELECT COUNT(*) FROM invoices i LEFT JOIN orders o ON i.OrderID=o.OrderID WHERE i.OrderID IS NOT NULL AND o.OrderID IS NULL",
    "orphan_transaction_customers": "SELECT COUNT(*) FROM customer_transactions t LEFT JOIN customers c ON t.CustomerID=c.CustomerID WHERE c.CustomerID IS NULL",
    "orphan_transaction_invoices": "SELECT COUNT(*) FROM customer_transactions t LEFT JOIN invoices i ON t.InvoiceID=i.InvoiceID WHERE t.InvoiceID IS NOT NULL AND i.InvoiceID IS NULL",
    "orphan_transaction_types": "SELECT COUNT(*) FROM customer_transactions t LEFT JOIN transaction_types d ON t.TransactionTypeID=d.TransactionTypeID WHERE d.TransactionTypeID IS NULL",
    "orphan_payment_methods": "SELECT COUNT(*) FROM customer_transactions t LEFT JOIN payment_methods d ON t.PaymentMethodID=d.PaymentMethodID WHERE t.PaymentMethodID IS NOT NULL AND d.PaymentMethodID IS NULL",
    "orphan_delivery_methods": "SELECT COUNT(*) FROM invoices i LEFT JOIN delivery_methods d ON i.DeliveryMethodID=d.DeliveryMethodID WHERE d.DeliveryMethodID IS NULL",
    "transactions_by_type": "SELECT d.TransactionTypeName,COUNT(*),SUM(t.TransactionAmount),SUM(CASE WHEN t.InvoiceID IS NULL THEN 1 ELSE 0 END),SUM(t.OutstandingBalance) FROM customer_transactions t JOIN transaction_types d ON t.TransactionTypeID=d.TransactionTypeID GROUP BY d.TransactionTypeName ORDER BY d.TransactionTypeName",
    "payments_by_method": "SELECT d.PaymentMethodName,COUNT(*),SUM(t.TransactionAmount) FROM customer_transactions t JOIN payment_methods d ON t.PaymentMethodID=d.PaymentMethodID GROUP BY d.PaymentMethodName ORDER BY d.PaymentMethodName",
    "delivery_coverage": "SELECT COUNT(*),SUM(CASE WHEN ConfirmedDeliveryTime IS NOT NULL THEN 1 ELSE 0 END),SUM(CASE WHEN ReturnedDeliveryData IS NOT NULL THEN 1 ELSE 0 END),SUM(CASE WHEN IsCreditNote=1 THEN 1 ELSE 0 END) FROM invoices",
    "unpicked_and_backorders": "SELECT SUM(CASE WHEN PickingCompletedWhen IS NULL THEN 1 ELSE 0 END),SUM(CASE WHEN BackorderOrderID IS NOT NULL THEN 1 ELSE 0 END) FROM orders",
    "order_invoice_multiplicity": "SELECT COUNT(*),MAX(n) FROM (SELECT OrderID,COUNT(*) n FROM invoices WHERE OrderID IS NOT NULL GROUP BY OrderID HAVING COUNT(*)>1) t",
    "uninvoiced_orders": "SELECT COUNT(*) FROM orders o LEFT JOIN invoices i ON o.OrderID=i.OrderID WHERE i.InvoiceID IS NULL",
    "invoice_balance": "SELECT SUM(TransactionAmount),SUM(OutstandingBalance),SUM(CASE WHEN IsFinalized=0 THEN 1 ELSE 0 END) FROM customer_transactions",
    "customer_balance_mismatches": "SELECT COUNT(*) FROM (SELECT CustomerID FROM customer_transactions GROUP BY CustomerID HAVING SUM(TransactionAmount)<>SUM(OutstandingBalance)) t",
    "invoice_billing_customer_mismatches": "SELECT COUNT(*) FROM customer_transactions t JOIN invoices i ON t.InvoiceID=i.InvoiceID WHERE t.CustomerID<>i.BillToCustomerID",
    "sample_sales_report": "SELECT o.OrderDate,COUNT(DISTINCT o.OrderID),SUM(l.Quantity*l.UnitPrice) FROM orders o JOIN order_lines l ON o.OrderID=l.OrderID JOIN customers c ON o.CustomerID=c.CustomerID JOIN products p ON l.StockItemID=p.StockItemID GROUP BY o.OrderDate ORDER BY o.OrderDate",
}


def profile(args):
    results = {}
    with pymysql.connect(host="127.0.0.1", port=args.doris_port, user="root",
                         password=os.environ.get("DW_PASSWORD", ""), database=args.database,
                         autocommit=True, read_timeout=300) as doris, source_connection(args.container) as source:
        checks = dict(CHECKS)
        for table, (_, columns) in TABLES.items():
            primary = columns.split()[0]
            checks[f"keys_{table}"] = f"SELECT COUNT(*),COUNT(DISTINCT {primary}) FROM {table}"
        for name, sql in checks.items():
            source_sql = sql
            for target, (original, _) in sorted(TABLES.items(), key=lambda item: -len(item[0])):
                source_sql = re.sub(r"\b" + target + r"\b", original, source_sql)
            expected = query(source, source_sql)
            actual = query(doris, sql)
            require([canonical(r) for r in actual] == [canonical(r) for r in expected], (name, actual, expected))
            if name.startswith("orphan_"):
                require(actual == ((0,),), (name, actual))
            if name.startswith("keys_"):
                require(actual[0][0] == actual[0][1], (name, actual))
            results[name] = {"sql": sql, "source_sql": source_sql, "result": actual}
            print("PROFILE", name, str(actual)[:1200] if name != "sample_sales_report" else f"{len(actual)} daily report rows match", flush=True)
    rows = pq.read_table(args.artifacts / "invoices.parquet", columns=["ReturnedDeliveryData"]).to_pylist()
    event_types = {}
    sample = None
    for row in rows:
        if row["ReturnedDeliveryData"] is not None:
            data = json.loads(row["ReturnedDeliveryData"])
            sample = data
            for event in data.get("Events", []):
                key = event.get("Event", "<no Event field>")
                event_types[key] = event_types.get(key, 0) + 1
    results["delivery_json"] = {"event_counts": event_types, "sample": sample}
    print("DELIVERY_JSON", event_types, sample, flush=True)
    save(args.artifacts / "profile-results.json", results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["restore", "export", "load", "profile"])
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--database", default="dw_course_l1_wwi_probe_20260918")
    parser.add_argument("--doris-port", type=int, default=19030)
    parser.add_argument("--be-http", type=int, default=18040)
    args = parser.parse_args()
    require(args.container.startswith("course02-wwi-validation-"), "Use a dedicated test container")
    require(re.fullmatch(r"dw_course_l1_wwi_probe_[a-z0-9_]+", args.database), "Use a dedicated test database")
    require(args.artifacts.is_dir(), "Artifact directory must exist")
    globals()[args.stage](args)


if __name__ == "__main__":
    main()
