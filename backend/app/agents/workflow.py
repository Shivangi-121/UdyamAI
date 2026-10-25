from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Expense, Product, Sale
from app.schemas.api import Recommendation
from app.services.calculations import unit_gross_margin


@dataclass
class AgentEvidence:
    role: str
    findings: list[str]
    missing: list[str]
    next_action: str


def _growth_agent(products: list[Product], sales: list[Sale]) -> AgentEvidence:
    count = len(sales)
    return AgentEvidence(
        "growth",
        [f"{count} recorded sales are available for review."],
        [] if count else ["Sales history is not available."],
        "Record a few sales, then review which products sell most." if not count else "Compare product sales over a consistent period.",
    )


def _inventory_agent(products: list[Product]) -> AgentEvidence:
    uncounted = [product.name for product in products if product.quantity is None]
    low = sorted((product for product in products if product.quantity is not None), key=lambda product: product.quantity or 0)
    findings = [f"{product.name}: {product.quantity} in recorded stock." for product in low[:3]]
    missing = [f"Stock count is missing for {name}." for name in uncounted]
    if not products:
        missing.append("No products have been entered.")
    return AgentEvidence("inventory", findings or ["No inventory evidence is available."], missing, "Count stock before deciding how much to reorder.")


def _profit_agent(products: list[Product]) -> AgentEvidence:
    missing = [f"Unit cost or selling price is missing for {product.name}." for product in products if product.cost is None or product.price is None]
    margins = [
        (product.name, unit_gross_margin(Decimal(product.price), Decimal(product.cost)))
        for product in products
        if product.cost is not None and product.price is not None
    ]
    ranked = sorted(margins, key=lambda item: item[1], reverse=True)
    findings = [f"{name}: entered gross margin is ₹{margin:.2f} per unit." for name, margin in ranked[:3]]
    return AgentEvidence("profit", findings or ["No product-level gross margin can be calculated yet."], missing, "Add unit cost and selling price before comparing margin changes.")


def _marketing_agent(question: str) -> AgentEvidence:
    return AgentEvidence(
        "marketing",
        ["Campaign ideas can be drafted for review; no message will be sent."],
        [],
        "Create an editable campaign draft if you want to explore an offer.",
    )


def coordinate_recommendation(db: Session, merchant_id: str, question: str, language: str) -> Recommendation:
    products = list(db.scalars(select(Product).where(Product.merchant_id == merchant_id)))
    sales = list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id)))
    expenses = list(db.scalars(select(Expense).where(Expense.merchant_id == merchant_id)))
    agents = [
        _growth_agent(products, sales),
        _inventory_agent(products),
        _profit_agent(products),
        _marketing_agent(question),
    ]
    observed = [finding for agent in agents for finding in agent.findings]
    missing = list(dict.fromkeys(item for agent in agents for item in agent.missing))
    evidence = [
        f"Merchant records: {len(sales)} sales, {len(expenses)} expenses, and {len(products)} products.",
        *[item for item in observed if "₹" in item or "in recorded stock" in item],
    ]
    if language == "hi":
        title = "कारोबार के लिए अगला कदम"
        message = "यह सुझाव दर्ज जानकारी पर आधारित है। जहाँ जानकारी कम है, वहाँ अनुमान लगाने के बजाय उसे स्पष्ट किया गया है।"
        next_action = agents[1].next_action if missing else agents[0].next_action
    else:
        title = "A practical next step"
        message = "This recommendation is based on recorded business information. Missing details are called out rather than guessed."
        next_action = agents[1].next_action if missing else agents[0].next_action
    return Recommendation(
        title=title,
        message=message,
        evidence=evidence,
        missing_information=missing,
        next_action=next_action,
        source="demo",
        observed_data=observed,
        assumptions=["The workflow uses entered records only; it does not predict demand or perform external actions."],
    )
