import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BusinessInsight, Expense, Merchant, Product, Sale
from app.schemas.api import InventoryRisk

CENT = Decimal("0.01")


def _json_list(value: str) -> list[str]:
    return json.loads(value)


def _inventory_risks(products: list[Product], sales: list[Sale], on: date) -> list[InventoryRisk]:
    since = on - timedelta(days=29)
    product_sales: dict[str, list[Sale]] = defaultdict(list)
    for sale in sales:
        if sale.product_id and since <= sale.date <= on:
            product_sales[sale.product_id].append(sale)

    risks = []
    for product in products:
        recent = product_sales[product.id]
        units = sum(sale.quantity for sale in recent)
        sales_days = len({sale.date for sale in recent})
        enough_history = units >= 3 and sales_days >= 3
        daily_rate = Decimal(units) / Decimal("30") if enough_history else None
        days_remaining = (
            (Decimal(product.quantity) / daily_rate).quantize(CENT)
            if daily_rate is not None and product.quantity is not None and daily_rate > 0
            else None
        )
        lead = product.supplier_lead_time_days
        suggested = None
        assumptions = []
        if not enough_history:
            assumptions.append("At least 3 units sold across 3 different days in the last 30 days are needed to estimate a sales rate.")
        if product.quantity is None:
            assumptions.append("Record an on-hand stock count to estimate stock coverage.")
        if lead is None:
            assumptions.append("Supplier lead time is not recorded; no replenishment quantity is estimated.")
        else:
            assumptions.append(f"Supplier lead time is recorded as {lead} days; a 3-day buffer is used for the suggested quantity.")
            if enough_history and product.quantity is not None and daily_rate is not None:
                suggested = max(0, int((daily_rate * Decimal(lead + 3)).to_integral_value(rounding=ROUND_CEILING)) - product.quantity)

        risk = "unknown"
        if enough_history and product.quantity is not None and days_remaining is not None:
            if lead is not None and days_remaining <= lead:
                risk = "high"
            elif (lead is None and days_remaining <= Decimal("3")) or (
                lead is not None and days_remaining <= Decimal(lead + 3)
            ):
                risk = "watch"
            else:
                risk = "low"
        risks.append(InventoryRisk(
            product_id=product.id,
            product_name=product.name,
            available_stock=product.quantity,
            units_sold=units,
            sales_days=sales_days,
            recent_daily_rate=daily_rate,
            estimated_days_remaining=days_remaining,
            supplier_lead_time_days=lead,
            risk=risk,
            suggested_replenishment=suggested,
            assumptions=assumptions,
        ))
    return risks


def analyze_merchant(db: Session, merchant_id: str, on: date | None = None) -> dict:
    today = on or date.today()
    now = datetime.now(timezone.utc)
    trend_threshold = Decimal(str(get_settings().intelligence_change_threshold))
    products = list(db.scalars(select(Product).where(Product.merchant_id == merchant_id)))
    merchant = db.get(Merchant, merchant_id)
    sales = list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id, Sale.date <= today)))
    expenses = list(db.scalars(select(Expense).where(Expense.merchant_id == merchant_id, Expense.date <= today)))
    db.query(BusinessInsight).filter(BusinessInsight.merchant_id == merchant_id).update(
        {BusinessInsight.is_active: False},
        synchronize_session=False,
    )
    inventory_risks = _inventory_risks(products, sales, today)
    active_days = {sale.date for sale in sales}
    maturity = "established" if len(active_days) >= 30 and (today - min(active_days)).days >= 90 else "emerging" if len(active_days) >= 3 else "new"
    findings: list[dict] = []
    by_date: dict[date, Decimal] = defaultdict(Decimal)
    for sale in sales:
        by_date[sale.date] += sale.amount

    current_start = today - timedelta(days=6)
    previous_start = today - timedelta(days=13)
    previous_end = today - timedelta(days=7)
    current_days = {day for day in by_date if current_start <= day <= today}
    previous_days = {day for day in by_date if previous_start <= day <= previous_end}
    if len(current_days) >= 3 and len(previous_days) >= 3:
        current_total = sum((by_date[day] for day in current_days), Decimal("0"))
        previous_total = sum((by_date[day] for day in previous_days), Decimal("0"))
        if previous_total > 0:
            change = (current_total - previous_total) / previous_total
            if abs(change) >= trend_threshold:
                direction = "increased" if change > 0 else "fallen"
                percent = abs(change * 100).quantize(Decimal("1"))
                findings.append({
                    "fingerprint": "sales-week-over-week",
                    "kind": "sales_trend",
                    "priority": 90 if change < 0 else 60,
                    "headline": f"Recorded sales have {direction} by about {percent}%",
                    "observed": f"Recorded sales were ₹{current_total:.2f} in the latest 7 days versus ₹{previous_total:.2f} in the 7 days before.",
                    "evidence": [f"{len(current_days)} selling days in the latest period.", f"{len(previous_days)} selling days in the comparison period."],
                    "comparison_period": f"{previous_start.isoformat()} to {previous_end.isoformat()} compared with {current_start.isoformat()} to {today.isoformat()}",
                    "why_it_matters": "A sustained change may be worth checking against stock availability, opening hours, or local events.",
                    "next_action": "Review recent sales and check whether stock or shop hours changed.",
                    "confidence": "medium",
                    "data_quality": "good",
                })

    period_expenses: dict[tuple[str, bool], list[Expense]] = defaultdict(list)
    for expense in expenses:
        if current_start <= expense.date <= today:
            period_expenses[(expense.category, True)].append(expense)
        elif previous_start <= expense.date <= previous_end:
            period_expenses[(expense.category, False)].append(expense)
    for category in {item.category for item in expenses}:
        recent = period_expenses[(category, True)]
        prior = period_expenses[(category, False)]
        if len(recent) < 2 or len(prior) < 2 or len({item.date for item in recent}) < 2 or len({item.date for item in prior}) < 2:
            continue
        recent_total = sum((item.amount for item in recent), Decimal("0"))
        prior_total = sum((item.amount for item in prior), Decimal("0"))
        if prior_total > 0 and recent_total >= prior_total * (Decimal("1") + trend_threshold):
            findings.append({
                "fingerprint": f"expense-category-{category.casefold()}",
                "kind": "expense_change",
                "priority": 55,
                "headline": f"Recorded {category.lower()} spending is higher",
                "observed": f"{category} expenses totaled ₹{recent_total:.2f} in the latest 7 days, up from ₹{prior_total:.2f}.",
                "evidence": [f"{len(recent)} entries in the latest period.", f"{len(prior)} entries in the comparison period."],
                "comparison_period": "Latest 7 days compared with the previous 7 days",
                "why_it_matters": "A change in recorded spending may be worth checking before planning other purchases.",
                "next_action": f"Review the {category.lower()} entries and confirm they are complete.",
                "confidence": "medium",
                "data_quality": "good",
            })

    for risk in inventory_risks:
        if risk.risk not in {"high", "watch"}:
            continue
        urgency = 100 if risk.risk == "high" else 80
        lead_label = f" before the {risk.supplier_lead_time_days}-day supplier lead time" if risk.supplier_lead_time_days is not None else " soon (supplier timing is not recorded)"
        findings.append({
            "fingerprint": f"stock-risk-{risk.product_id}",
            "kind": "inventory_risk",
            "entity_id": risk.product_id,
            "priority": urgency,
            "headline": f"{risk.product_name} may run low",
            "observed": f"{risk.available_stock} in stock; recorded sales suggest about {risk.estimated_days_remaining} days of stock remain.",
            "evidence": [f"{risk.units_sold} units sold across {risk.sales_days} days in the last 30 days.", *risk.assumptions],
            "comparison_period": "Recent 30-day recorded sales rate",
            "why_it_matters": f"Current stock may not last{lead_label}.",
            "next_action": "Compare a replenishment amount in Business Twin before deciding.",
            "confidence": "medium" if risk.risk == "high" else "low",
            "data_quality": "good" if risk.supplier_lead_time_days is not None else "limited",
        })

    recent_by_product: dict[str, list[Sale]] = defaultdict(list)
    for sale in sales:
        if sale.product_id and today - timedelta(days=29) <= sale.date <= today:
            recent_by_product[sale.product_id].append(sale)
    for product in products:
        recent = recent_by_product[product.id]
        units = sum(sale.quantity for sale in recent)
        if product.cost is None or units < 3 or len({sale.date for sale in recent}) < 3:
            continue
        average_price = sum((sale.amount for sale in recent), Decimal("0")) / Decimal(units)
        if average_price <= 0:
            continue
        gross_margin = average_price - product.cost
        margin_percent = gross_margin / average_price * 100
        if margin_percent <= 10:
            findings.append({
                "fingerprint": f"low-margin-{product.id}",
                "kind": "low_margin",
                "entity_id": product.id,
                "priority": 75,
                "headline": f"Check the cost and price for {product.name}",
                "observed": f"Across {units} recorded units, the current entered unit cost and recent average sale amount suggest about ₹{gross_margin:.2f} gross margin per item ({margin_percent:.1f}%).",
                "evidence": [
                    f"Sales were recorded on {len({sale.date for sale in recent})} different days in the last 30 days.",
                    f"Current entered unit cost: ₹{product.cost:.2f}.",
                    "Average sale amount is based on recorded sale totals divided by recorded quantities.",
                ],
                "comparison_period": "Recent 30-day product sales and current entered unit cost",
                "why_it_matters": "A narrow or negative gross margin leaves less room to cover other shop expenses; this is not net profit.",
                "next_action": "Check whether the supplier cost and selling price are still correct before offering a discount.",
                "confidence": "medium",
                "data_quality": "good",
            })

    for finding in findings:
        existing = db.scalar(select(BusinessInsight).where(
            BusinessInsight.merchant_id == merchant_id,
            BusinessInsight.fingerprint == finding["fingerprint"],
        ))
        if existing:
            for key, value in finding.items():
                if key not in {"fingerprint", "evidence"}:
                    setattr(existing, key, value)
            existing.evidence = json.dumps(finding["evidence"])
            existing.evaluated_at = now
            existing.is_active = True
        else:
            db.add(BusinessInsight(
                id=str(uuid4()),
                merchant_id=merchant_id,
                fingerprint=finding["fingerprint"],
                evidence=json.dumps(finding["evidence"]),
                status="unread",
                is_active=True,
                generated_at=now,
                evaluated_at=now,
                **{key: value for key, value in finding.items() if key not in {"fingerprint", "evidence"}},
            ))
    db.flush()
    stored = list(db.scalars(select(BusinessInsight).where(
        BusinessInsight.merchant_id == merchant_id,
        BusinessInsight.status != "dismissed",
        (BusinessInsight.is_active.is_(True)) | (BusinessInsight.status == "saved"),
    )))
    insights = sorted(stored, key=lambda item: (-item.priority, -item.generated_at.timestamp()))[:5]
    db.commit()
    missing = []
    if not sales:
        missing.append("Record sales on different days to identify changes; no personalized sales trend is available yet.")
    elif len(active_days) < 3:
        missing.append("More recorded sales days are needed before comparing business trends.")
    if any(product.quantity is None for product in products):
        missing.append("Add current stock counts to check potential shortages.")
    if any(product.supplier_lead_time_days is None for product in products):
        missing.append("Supplier lead times are missing for some products; replenishment timing is less certain.")
    last_sale = max((sale.date for sale in sales), default=None)
    if last_sale and (today - last_sale).days > 30:
        missing.append(f"The latest recorded sale is from {last_sale.isoformat()}; current recommendations may be stale.")
    return {
        "generated_at": now,
        "maturity": maturity,
        "insights": [_serialize_insight(item) for item in insights],
        "inventory_risks": [item.model_dump(mode="json") for item in inventory_risks],
        "missing_information": missing,
        "source": "demo_data" if merchant and merchant.is_demo else "recorded_data",
    }


def _serialize_insight(item: BusinessInsight) -> dict:
    return {
        "id": item.id,
        "merchant_id": item.merchant_id,
        "kind": item.kind,
        "entity_id": item.entity_id,
        "priority": item.priority,
        "headline": item.headline,
        "observed": item.observed,
        "evidence": _json_list(item.evidence),
        "comparison_period": item.comparison_period,
        "why_it_matters": item.why_it_matters,
        "next_action": item.next_action,
        "confidence": item.confidence,
        "data_quality": item.data_quality,
        "status": item.status,
        "is_active": item.is_active,
        "generated_at": item.generated_at,
        "evaluated_at": item.evaluated_at,
    }
