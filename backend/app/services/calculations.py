from decimal import Decimal, ROUND_HALF_UP
from collections.abc import Sequence

from app.schemas.api import Projection, ScenarioInput, ScenarioResult
from app.models import Expense, Sale

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def unit_gross_margin(price: Decimal, cost: Decimal) -> Decimal:
    return money(price - cost)


def project(inventory: int, demand: int, price: Decimal, cost: Decimal, discount: Decimal) -> Projection:
    sold = min(inventory, demand)
    discounted_price = price * (Decimal("1") - discount / Decimal("100"))
    revenue = money(discounted_price * sold)
    cogs = money(cost * sold)
    return Projection(
        inventory=inventory,
        demand=demand,
        units_sold=sold,
        revenue=revenue,
        cost_of_goods_sold=cogs,
        gross_profit=money(revenue - cogs),
        unsold_units=inventory - sold,
    )


def simulate_scenario(input: ScenarioInput) -> ScenarioResult:
    forecast_demand = input.demand_per_day * input.period
    baseline = project(
        input.available_inventory,
        forecast_demand,
        input.price,
        input.cost,
        Decimal("0"),
    )
    proposed = project(
        input.available_inventory + input.extra_stock,
        forecast_demand,
        input.price,
        input.cost,
        input.discount,
    )
    assumptions = [
        f"The entered demand assumption is {input.demand_per_day} units per day for {input.period} days.",
        "Units sold are capped by available stock; no historical demand forecast is inferred.",
        "Gross profit is revenue less cost of goods sold and excludes other expenses.",
    ]
    if input.supplier_lead_time_days is not None:
        assumptions.append(f"Supplier lead time is {input.supplier_lead_time_days} days; no replenishment during this scenario is modeled.")
    limitations = [
        "Actual demand, spoilage, taxes, fees, and other operating expenses may differ.",
        "Unsold stock remains inventory and is not subtracted from gross profit.",
    ]
    if input.extra_stock < forecast_demand - input.available_inventory:
        limitations.append("Proposed stock may still be below the entered demand assumption.")
    return ScenarioResult(
        baseline=baseline,
        proposed=proposed,
        differences={
            "units_sold": proposed.units_sold - baseline.units_sold,
            "revenue": money(proposed.revenue - baseline.revenue),
            "cost_of_goods_sold": money(proposed.cost_of_goods_sold - baseline.cost_of_goods_sold),
            "gross_profit": money(proposed.gross_profit - baseline.gross_profit),
            "unsold_units": proposed.unsold_units - baseline.unsold_units,
        },
        assumptions=assumptions,
        limitations=limitations,
    )


def aggregate_metrics(
    sales_count: int,
    revenue: Decimal,
    costed_sales_count: int,
    cost_of_goods: Decimal,
    expenses_count: int,
    recorded_expenses: Decimal,
) -> dict:
    revenue = money(revenue)
    cogs_known = sales_count > 0 and costed_sales_count == sales_count
    cost_of_goods = money(cost_of_goods)
    recorded_expenses = money(recorded_expenses)
    missing_information = (
        ["No sales are recorded for this period; profit is unavailable."]
        if sales_count == 0
        else ["Cost of goods is missing for one or more sales."]
        if not cogs_known
        else []
    )
    return {
        "sales_count": sales_count,
        "expenses_count": expenses_count,
        "revenue": str(revenue),
        "recorded_expenses": str(recorded_expenses),
        "gross_profit": str(money(revenue - cost_of_goods)) if cogs_known else None,
        "gross_profit_available": cogs_known,
        "missing_information": missing_information,
    }


def recorded_metrics(sales: Sequence[Sale], expenses: Sequence[Expense]) -> dict:
    return aggregate_metrics(
        sales_count=len(sales),
        revenue=sum((sale.amount for sale in sales), Decimal("0")),
        costed_sales_count=sum(sale.cost_of_goods is not None for sale in sales),
        cost_of_goods=sum((sale.cost_of_goods or Decimal("0") for sale in sales), Decimal("0")),
        expenses_count=len(expenses),
        recorded_expenses=sum((expense.amount for expense in expenses), Decimal("0")),
    )
