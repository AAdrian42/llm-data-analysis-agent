from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from .semantic_layer import RAW_COLUMNS, TABLE_NAME


class UnsafeSQLError(ValueError):
    pass


DISALLOWED_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|copy|attach|detach|pragma|install|load|call|export|import|vacuum)\b",
    flags=re.IGNORECASE,
)

EXTERNAL_PATTERN = re.compile(
    r"\b(read_csv|read_csv_auto|read_parquet|read_json|httpfs|sqlite_scan|postgres_scan|mysql_scan)\s*\(",
    flags=re.IGNORECASE,
)


def validate_readonly_sql(sql: str, max_limit: int = 5000) -> str:
    stripped = sql.strip()
    if not stripped:
        raise UnsafeSQLError("SQL is empty")
    if ";" in stripped:
        raise UnsafeSQLError("Multiple statements and semicolons are not allowed")
    if "--" in stripped or "/*" in stripped:
        raise UnsafeSQLError("SQL comments are not allowed")
    if DISALLOWED_PATTERN.search(stripped):
        raise UnsafeSQLError("DDL, DML and database commands are not allowed")
    if EXTERNAL_PATTERN.search(stripped):
        raise UnsafeSQLError("External file and network readers are not allowed")

    statements = sqlglot.parse(stripped, read="duckdb")
    if len(statements) != 1:
        raise UnsafeSQLError("Exactly one statement is required")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise UnsafeSQLError("Only SELECT queries are allowed")

    tables = {table.name for table in tree.find_all(exp.Table)}
    if tables != {TABLE_NAME}:
        raise UnsafeSQLError(f"Only table {TABLE_NAME} is allowed; found {sorted(tables)}")

    allowed_aliases = {
        "metric_value",
        "sample_size",
        "metric_sample_size",
        "application_month",
        "application_year",
        "dti_band",
        "fico_band",
        "loan_amount_band",
    }
    for column in tree.find_all(exp.Column):
        if column.name not in RAW_COLUMNS | allowed_aliases:
            raise UnsafeSQLError(f"Column is not allowed: {column.name}")

    limit_node = tree.args.get("limit")
    if limit_node is None:
        raise UnsafeSQLError("A LIMIT clause is required")
    try:
        limit_value = int(limit_node.expression.name)
    except (AttributeError, TypeError, ValueError) as exc:
        raise UnsafeSQLError("LIMIT must be a fixed integer") from exc
    if not 1 <= limit_value <= max_limit:
        raise UnsafeSQLError(f"LIMIT must be between 1 and {max_limit}")
    return stripped

