import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Expense, Product, Sale
from app.services.calculations import money

RecordType = Literal["sales", "expenses", "products"]
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 5000
MAX_INTEGER = 2_147_483_647

FIELDS: dict[str, tuple[str, ...]] = {
    "sales": ("date", "amount", "quantity", "product_name", "unit_price", "cost_of_goods", "note"),
    "expenses": ("date", "amount", "category", "note"),
    "products": ("name", "category", "quantity", "cost", "price", "supplier_lead_time_days"),
}
REQUIRED_FIELDS = {"sales": ("date", "amount"), "expenses": ("date", "amount"), "products": ("name",)}
ALIASES = {
    "date": {"date", "sale date", "sale day", "expense date", "transaction date"},
    "amount": {"amount", "total", "total amount", "revenue", "sale amount", "expense amount"},
    "quantity": {"quantity", "qty", "units"},
    "product_name": {"product", "product name", "item", "item name"},
    "unit_price": {"unit price", "price per unit"},
    "cost_of_goods": {"cost of goods", "cost of goods sold", "cogs"},
    "note": {"note", "description", "reference"},
    "category": {"category", "expense category"},
    "name": {"name", "product name", "product"},
    "cost": {"cost", "unit cost"},
    "price": {"price", "selling price", "unit price"},
    "supplier_lead_time_days": {"supplier lead time days", "lead time days"},
}


def decode_csv(raw: bytes, filename: str | None, content_type: str | None) -> tuple[str, str]:
    if not filename or not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv file.")
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV files must be 2 MB or smaller.")
    if content_type and content_type.lower() not in {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="The uploaded file content type is not supported.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must use UTF-8 encoding.") from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="The CSV file is empty.")
    return text, hashlib.sha256(raw).hexdigest()


def _read_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = reader.fieldnames or []
        if not headers or any(not item or not item.strip() for item in headers):
            raise HTTPException(status_code=422, detail="CSV must have a non-empty header row.")
        normalized = [item.strip().casefold() for item in headers]
        if len(normalized) != len(set(normalized)):
            raise HTTPException(status_code=422, detail="CSV column names must be unique.")
        rows = []
        for index, row in enumerate(reader, start=1):
            if index > MAX_CSV_ROWS:
                raise HTTPException(status_code=413, detail=f"CSV files may contain at most {MAX_CSV_ROWS} data rows.")
            if None in row:
                raise HTTPException(status_code=422, detail=f"CSV row {index + 1} has more values than the header.")
            rows.append({str(key): (value or "").strip() for key, value in row.items() if key is not None})
        return headers, rows
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail="The CSV structure is invalid.") from exc


def _default_mapping(record_type: str, headers: list[str]) -> dict[str, str]:
    by_normalized = {header.strip().casefold(): header for header in headers}
    mapping: dict[str, str] = {}
    for field in FIELDS[record_type]:
        for alias in ALIASES.get(field, {field}):
            if alias.casefold() in by_normalized:
                mapping[field] = by_normalized[alias.casefold()]
                break
    return mapping


def _resolve_mapping(
    record_type: str,
    headers: list[str],
    mapping_json: str | None,
) -> dict[str, str]:
    if not mapping_json:
        mapping = _default_mapping(record_type, headers)
    else:
        try:
            mapping = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Column mapping must be valid JSON.") from exc
        if not isinstance(mapping, dict) or any(
            not isinstance(field, str) or not isinstance(header, str)
            for field, header in mapping.items()
        ):
            raise HTTPException(status_code=422, detail="Column mapping must map field names to CSV column names.")
        if any(field not in FIELDS[record_type] for field in mapping):
            raise HTTPException(status_code=422, detail="Column mapping contains an unsupported field.")
        if any(header not in headers for header in mapping.values()):
            raise HTTPException(status_code=422, detail="Column mapping refers to a column not present in the CSV.")
        if len(set(mapping.values())) != len(mapping.values()):
            raise HTTPException(status_code=422, detail="Each CSV column can be mapped to only one UdyamAI field.")
    return mapping


def _decimal(value: str, field: str, required: bool = False) -> Decimal | None:
    if not value:
        if required:
            raise ValueError(f"{field} is required.")
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal number.") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError(f"{field} must be a non-negative amount with at most two decimal places.")
    if amount > Decimal("9999999999.99"):
        raise ValueError(f"{field} is too large.")
    return money(amount)


def _date(value: str) -> date:
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc
    if result.isoformat() != value:
        raise ValueError("Date must use YYYY-MM-DD format.")
    return result


def _integer(value: str, field: str, default: int | None = None) -> int | None:
    if not value:
        return default
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a whole number.") from exc
    if result < 0:
        raise ValueError(f"{field} cannot be negative.")
    if result > MAX_INTEGER:
        raise ValueError(f"{field} is too large.")
    return result


def _fingerprint(merchant_id: str, record_type: str, record: dict[str, Any]) -> str:
    canonical = {
        key: value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, Decimal) else value
        for key, value in record.items()
    }
    payload = json.dumps([merchant_id, record_type, canonical], sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def import_preview_digest(file_digest: str, record_type: str, mapping: dict[str, str]) -> str:
    payload = json.dumps(
        [file_digest, record_type, mapping],
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_import(
    db: Session,
    merchant_id: str,
    record_type: RecordType,
    text: str,
    mapping_json: str | None,
) -> dict:
    headers, source_rows = _read_rows(text)
    mapping = _resolve_mapping(record_type, headers, mapping_json)
    missing_fields = [field for field in REQUIRED_FIELDS[record_type] if field not in mapping]
    if missing_fields:
        return {
            "record_type": record_type,
            "headers": headers,
            "mapping": mapping,
            "missing_required_fields": missing_fields,
            "valid_count": 0,
            "skipped_count": 0,
            "invalid_count": 0,
            "rows": [],
        }

    products = list(db.scalars(select(Product).where(Product.merchant_id == merchant_id)))
    products_by_name: dict[str, list[Product]] = {}
    for product in products:
        products_by_name.setdefault(product.name.strip().casefold(), []).append(product)
    existing_product_names = set(products_by_name)
    seen_product_names: set[str] = set()
    parsed_rows = []
    used_fingerprints: set[str] = set()
    for row_number, source_row in enumerate(source_rows, start=2):
        if not any(value.strip() for value in source_row.values()):
            continue
        values = {
            field: source_row.get(header, "").strip()
            for field, header in mapping.items()
        }
        errors: list[str] = []
        record: dict[str, Any] = {}
        resolved_product = None
        try:
            if record_type in {"sales", "expenses"}:
                record["date"] = _date(values.get("date", ""))
                record["amount"] = _decimal(values.get("amount", ""), "Amount", required=True)
                if record["amount"] <= 0:
                    raise ValueError("Amount must be greater than zero.")
            if record_type == "sales":
                record["quantity"] = _integer(values.get("quantity", ""), "Quantity", default=1)
                if not record["quantity"]:
                    raise ValueError("Quantity must be greater than zero.")
                record["unit_price"] = _decimal(values.get("unit_price", ""), "Unit price")
                record["cost_of_goods"] = _decimal(values.get("cost_of_goods", ""), "Cost of goods")
                record["note"] = values.get("note", "")
                if len(record["note"]) > 500:
                    raise ValueError("Note must be 500 characters or fewer.")
                product_name = values.get("product_name", "").strip()
                if product_name:
                    matches = products_by_name.get(product_name.casefold(), [])
                    if len(matches) != 1:
                        raise ValueError("Product name must match exactly one product in this merchant's catalog.")
                    resolved_product = matches[0]
                record["product_id"] = resolved_product.id if resolved_product else None
                if record["unit_price"] is not None and record["unit_price"] * record["quantity"] != record["amount"]:
                    raise ValueError("Amount must equal unit price multiplied by quantity.")
            elif record_type == "expenses":
                record["category"] = values.get("category", "Other") or "Other"
                record["note"] = values.get("note", "")
                if len(record["category"]) > 100 or len(record["note"]) > 500:
                    raise ValueError("Category must be at most 100 characters and note at most 500.")
            else:
                record["name"] = values.get("name", "").strip()
                record["category"] = values.get("category", "").strip() or None
                record["quantity"] = _integer(values.get("quantity", ""), "Quantity")
                record["cost"] = _decimal(values.get("cost", ""), "Cost")
                record["price"] = _decimal(values.get("price", ""), "Price")
                record["supplier_lead_time_days"] = _integer(values.get("supplier_lead_time_days", ""), "Supplier lead time")
                if record["supplier_lead_time_days"] is not None and record["supplier_lead_time_days"] > 365:
                    raise ValueError("Supplier lead time must be 365 days or fewer.")
                if not record["name"]:
                    raise ValueError("Product name is required.")
                if len(record["name"]) > 160 or (record["category"] and len(record["category"]) > 100):
                    raise ValueError("Product name must be at most 160 characters and category at most 100.")
                normalized_name = record["name"].casefold()
                if normalized_name in existing_product_names or normalized_name in seen_product_names:
                    errors.append("Product already exists; existing products are not overwritten by imports.")
                seen_product_names.add(normalized_name)
        except (ValueError, InvalidOperation) as exc:
            errors.append(str(exc))

        fingerprint = None
        if not errors and record_type in {"sales", "expenses"}:
            fingerprint = _fingerprint(merchant_id, record_type, record)
            if fingerprint in used_fingerprints:
                errors.append("Duplicate of another row in this file; only the first matching row is considered.")
            else:
                model = Sale if record_type == "sales" else Expense
                already_imported = db.scalar(select(model.id).where(
                    model.merchant_id == merchant_id,
                    model.import_fingerprint == fingerprint,
                ))
                if already_imported:
                    errors.append("This exact record was already imported; duplicate rows are skipped.")
                used_fingerprints.add(fingerprint)

        duplicate = any(
            "already exists" in error or "already imported" in error or "Duplicate" in error
            for error in errors
        )
        parsed_rows.append({
            "row": row_number,
            "status": "skipped" if errors and duplicate else "invalid" if errors else "valid",
            "errors": errors,
            "record": record if not errors else None,
            "fingerprint": fingerprint if not errors else None,
            "display": _display_record(record, record_type, resolved_product) if not errors else values,
        })

    return {
        "record_type": record_type,
        "headers": headers,
        "mapping": mapping,
        "missing_required_fields": [],
        "valid_count": sum(item["status"] == "valid" for item in parsed_rows),
        "skipped_count": sum(item["status"] == "skipped" for item in parsed_rows),
        "invalid_count": sum(item["status"] == "invalid" for item in parsed_rows),
        "rows": parsed_rows,
    }


def _display_record(record: dict[str, Any], record_type: str, product: Product | None) -> dict[str, Any]:
    result = {}
    for key, value in record.items():
        if key == "product_id":
            result["product_name"] = product.name if product else ""
        elif isinstance(value, (date, Decimal)):
            result[key] = str(value)
        else:
            result[key] = value
    if record_type == "products":
        result["category"] = record.get("category") or ""
    return result


def export_csv(record_type: RecordType, records: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    if record_type == "sales":
        headers = ("date", "amount", "quantity", "product_name", "unit_price", "cost_of_goods", "note", "source")
    elif record_type == "expenses":
        headers = ("date", "amount", "category", "note", "source")
    else:
        headers = ("name", "category", "quantity", "cost", "price", "supplier_lead_time_days")
    writer.writerow(headers)
    for record in records:
        writer.writerow([_safe_cell(record.get(header, "")) for header in headers])
    return output.getvalue()


def _safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text
