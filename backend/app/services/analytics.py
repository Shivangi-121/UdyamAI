from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Expense, Merchant, Product, Sale
from app.services.calculations import aggregate_metrics, money


def _sale_totals(
    db: Session,
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[int, Decimal, int, Decimal]:
    query = select(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.amount), 0),
        func.count(Sale.cost_of_goods),
        func.coalesce(func.sum(Sale.cost_of_goods), 0),
    ).where(Sale.merchant_id == merchant_id)
    if start_date is not None:
        query = query.where(Sale.date >= start_date)
    if end_date is not None:
        query = query.where(Sale.date <= end_date)
    count, revenue, costed_count, cost_of_goods = db.execute(query).one()
    return int(count), Decimal(revenue), int(costed_count), Decimal(cost_of_goods)


def _expense_totals(
    db: Session,
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[int, Decimal]:
    query = select(
        func.count(Expense.id),
        func.coalesce(func.sum(Expense.amount), 0),
    ).where(Expense.merchant_id == merchant_id)
    if start_date is not None:
        query = query.where(Expense.date >= start_date)
    if end_date is not None:
        query = query.where(Expense.date <= end_date)
    count, amount = db.execute(query).one()
    return int(count), Decimal(amount)


def merchant_recorded_metrics(
    db: Session,
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    sales_count, revenue, costed_count, cost_of_goods = _sale_totals(
        db, merchant_id, start_date, end_date
    )
    expenses_count, recorded_expenses = _expense_totals(
        db, merchant_id, start_date, end_date
    )
    return aggregate_metrics(
        sales_count,
        revenue,
        costed_count,
        cost_of_goods,
        expenses_count,
        recorded_expenses,
    )


def merchant_analytics(
    db: Session,
    merchant_id: str,
    start_date: date,
    end_date: date,
) -> dict:
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise ValueError("Merchant not found")

    sales_count, revenue, costed_count, cost_of_goods = _sale_totals(
        db, merchant_id, start_date, end_date
    )
    expenses_count, recorded_expenses = _expense_totals(
        db, merchant_id, start_date, end_date
    )
    values = aggregate_metrics(
        sales_count,
        revenue,
        costed_count,
        cost_of_goods,
        expenses_count,
        recorded_expenses,
    )
    gross_profit = Decimal(values["gross_profit"]) if values["gross_profit"] is not None else None
    products = list(db.scalars(
        select(Product).where(Product.merchant_id == merchant_id).order_by(Product.name)
    ))
    products_by_id = {product.id: product for product in products}
    product_cost_count = sum(product.cost is not None for product in products)
    inventory_configured = bool(products) and all(product.quantity is not None for product in products)

    sales_by_day = dict(db.execute(
        select(Sale.date, func.sum(Sale.amount))
        .where(
            Sale.merchant_id == merchant_id,
            Sale.date >= start_date,
            Sale.date <= end_date,
        )
        .group_by(Sale.date)
    ).all())
    expenses_by_day = dict(db.execute(
        select(Expense.date, func.sum(Expense.amount))
        .where(
            Expense.merchant_id == merchant_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .group_by(Expense.date)
    ).all())
    days = (end_date - start_date).days + 1
    trend = [
        {
            "date": (start_date + timedelta(days=offset)).isoformat(),
            "sales": str(money(Decimal(sales_by_day.get(start_date + timedelta(days=offset), 0)))),
            "expenses": str(money(Decimal(expenses_by_day.get(start_date + timedelta(days=offset), 0)))),
        }
        for offset in range(days)
    ]

    expense_categories = db.execute(
        select(Expense.category, func.sum(Expense.amount))
        .where(
            Expense.merchant_id == merchant_id,
            Expense.date >= start_date,
            Expense.date <= end_date,
        )
        .group_by(Expense.category)
    ).all()
    products_performance = db.execute(
        select(
            Sale.product_id,
            func.sum(Sale.amount),
            func.sum(Sale.quantity),
            func.count(Sale.id),
        )
        .where(
            Sale.merchant_id == merchant_id,
            Sale.product_id.is_not(None),
            Sale.date >= start_date,
            Sale.date <= end_date,
        )
        .group_by(Sale.product_id)
        .order_by(func.sum(Sale.amount).desc())
        .limit(10)
    ).all()
    best_products = [
        {
            "product_id": product_id,
            "name": products_by_id[product_id].name if product_id in products_by_id else "Deleted product",
            "revenue": str(money(Decimal(amount))),
            "quantity_sold": int(quantity),
            "sales_count": int(count),
        }
        for product_id, amount, quantity, count in products_performance
    ]

    previous_start = start_date - timedelta(days=days)
    previous_end = start_date - timedelta(days=1)
    coverage_start = min(filter(None, [
        db.scalar(select(func.min(Sale.date)).where(Sale.merchant_id == merchant_id)),
        db.scalar(select(func.min(Expense.date)).where(Expense.merchant_id == merchant_id)),
    ]), default=None)
    coverage_end = max(filter(None, [
        db.scalar(select(func.max(Sale.date)).where(Sale.merchant_id == merchant_id)),
        db.scalar(select(func.max(Expense.date)).where(Expense.merchant_id == merchant_id)),
    ]), default=None)
    comparison_available = coverage_start is not None and coverage_start <= previous_start
    period_comparison = None
    if comparison_available:
        prior_sales_count, prior_revenue, _, _ = _sale_totals(
            db, merchant_id, previous_start, previous_end
        )
        prior_expenses_count, prior_expenses = _expense_totals(
            db, merchant_id, previous_start, previous_end
        )
        prior_metrics = aggregate_metrics(
            prior_sales_count,
            prior_revenue,
            0,
            Decimal("0"),
            prior_expenses_count,
            prior_expenses,
        )
        prior_categories = db.execute(
            select(Expense.category, func.sum(Expense.amount))
            .where(
                Expense.merchant_id == merchant_id,
                Expense.date >= previous_start,
                Expense.date <= previous_end,
            )
            .group_by(Expense.category)
        ).all()
        period_comparison = {
            "start_date": previous_start.isoformat(),
            "end_date": previous_end.isoformat(),
            "revenue": prior_metrics["revenue"],
            "recorded_expenses": prior_metrics["recorded_expenses"],
            "expenses_by_category": [
                {"category": category, "amount": str(money(Decimal(amount)))}
                for category, amount in prior_categories
            ],
        }

    sales_exist = _sale_totals(db, merchant_id)[0] > 0
    expenses_exist = _expense_totals(db, merchant_id)[0] > 0
    missing_information = list(values["missing_information"])
    if not expenses_count:
        missing_information.append("No expenses are recorded for this period.")
    if products and product_cost_count < len(products):
        missing_information.append("Some product costs are missing; product margin estimates may be incomplete.")
    if products and not inventory_configured:
        missing_information.append("Inventory coverage is incomplete because one or more product stock counts are not set.")
    if not comparison_available:
        missing_information.append(
            "A comparable earlier period is unavailable because recorded history does not cover the full comparison range."
        )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "currency": merchant.currency,
        "metrics": {
            "sales_count": sales_count,
            "expenses_count": expenses_count,
            "revenue": values["revenue"],
            "recorded_expenses": values["recorded_expenses"],
            "gross_profit": values["gross_profit"],
            "net_profit": (
                str(money(gross_profit - Decimal(values["recorded_expenses"])))
                if gross_profit is not None else None
            ),
            "gross_profit_available": values["gross_profit_available"],
            "average_sale_value": str(money(revenue / sales_count)) if sales_count else None,
        },
        "trend": trend,
        "expenses_by_category": [
            {"category": category, "amount": str(money(Decimal(amount)))}
            for category, amount in sorted(expense_categories, key=lambda item: item[1], reverse=True)
        ],
        "best_performing_products": best_products,
        "comparison": {
            "available": comparison_available,
            "previous_period": period_comparison,
            "warning": (
                "The comparison uses recorded entries only; completeness of bookkeeping cannot be verified."
                if comparison_available else None
            ),
        },
        "coverage": {
            "sales_recorded": sales_exist,
            "expenses_recorded": expenses_exist,
            "product_count": len(products),
            "products_with_cost": product_cost_count,
            "inventory_configured": inventory_configured,
            "period_start": coverage_start.isoformat() if coverage_start else None,
            "period_end": coverage_end.isoformat() if coverage_end else None,
            "missing_information": list(dict.fromkeys(missing_information)),
            "suggestions": _coverage_suggestions(
                sales_exist=sales_exist,
                expenses_exist=expenses_exist,
                products=products,
                coverage_start=coverage_start,
            ),
        },
    }


def _coverage_suggestions(
    sales_exist: bool,
    expenses_exist: bool,
    products: list[Product],
    coverage_start: date | None,
) -> list[str]:
    suggestions = []
    if not sales_exist:
        suggestions.append("Record sales or import previous sales to compare trends.")
    if not expenses_exist:
        suggestions.append("Record expenses to understand net profitability.")
    if any(product.cost is None for product in products):
        suggestions.append("Add product costs to estimate gross margins.")
    if any(product.quantity is None for product in products):
        suggestions.append("Set product stock counts to receive inventory warnings.")
    if coverage_start is not None:
        suggestions.append(f"Recorded history starts on {coverage_start.isoformat()}; older business activity is not represented.")
    return suggestions
