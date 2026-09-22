"""Shared order contract; notebooks print the actual DDL before executing it."""

from .runtime import identifier

ORDER_COLUMNS = (
    "order_id", "customer_id", "order_amount", "status", "event_version",
    "event_id", "event_time", "paid_amount", "refund_amount", "region", "data_source",
)
ORDER_TYPES = {
    "order_id": "BIGINT NOT NULL",
    "customer_id": "BIGINT NOT NULL",
    "order_amount": "DECIMAL(12,2) NOT NULL",
    "status": "VARCHAR(20) NOT NULL",
    "event_version": "BIGINT NOT NULL",
    "event_id": "VARCHAR(32) NOT NULL",
    "event_time": "DATETIME NOT NULL",
    "paid_amount": "DECIMAL(12,2) NOT NULL",
    "refund_amount": "DECIMAL(12,2) NOT NULL",
    "region": "VARCHAR(16) NOT NULL",
    "data_source": "VARCHAR(32) NOT NULL",
}


def order_ddl(table, *, current=False, history=False):
    if current and history:
        raise ValueError("A table cannot be both current state and history")
    table = identifier(table)
    key = "event_id" if history else "order_id"
    columns = (key,) + tuple(col for col in ORDER_COLUMNS if col != key)
    fields = ",\n    ".join(f"{col} {ORDER_TYPES[col]}" for col in columns)
    model = "UNIQUE" if current or history else "DUPLICATE"
    properties = ['"replication_num"="1"']
    if current or history:
        properties.append('"enable_unique_key_merge_on_write"="true"')
    if current:
        properties.append('"function_column.sequence_col"="event_version"')
    return (
        f"CREATE TABLE {table} (\n    {fields}\n)\n"
        f"{model} KEY({key})\nDISTRIBUTED BY HASH({key}) BUCKETS 1\n"
        f"PROPERTIES ({', '.join(properties)})"
    )


def order_rows(records):
    return [tuple(record[col] for col in ORDER_COLUMNS) for record in records]
