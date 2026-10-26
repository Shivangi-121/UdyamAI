import argparse
from datetime import timedelta

from app.core.time import business_today
from app.db.session import SessionLocal
from app.models import (
    ActionHistory,
    AIRecommendation,
    AutopilotTask,
    BusinessInsight,
    CampaignDraft,
    Expense,
    InventoryRecord,
    Merchant,
    Product,
    RecommendationOutcome,
    Sale,
    Scenario,
)
from app.schemas.api import ScenarioInput
from app.services.calculations import simulate_scenario
from app.services.intelligence import analyze_merchant


def demo_data():
    coconuts = [
        {"id": "coconut", "name": "Fresh coconuts", "quantity": 32, "cost": 20, "price": 35, "category": "Fresh produce"},
        {"id": "water", "name": "Coconut water", "quantity": 18, "cost": 8, "price": 25, "category": "Drinks"},
        {"id": "lime", "name": "Limes", "quantity": 45, "cost": 2, "price": 5, "category": "Fresh produce"},
    ]
    kirana = [
        {"id": "rice", "name": "Basmati rice (1 kg)", "quantity": 28, "cost": 72, "price": 92, "category": "Staples"},
        {"id": "dal", "name": "Toor dal (1 kg)", "quantity": 21, "cost": 96, "price": 120, "category": "Staples"},
        {"id": "oil", "name": "Cooking oil (1 L)", "quantity": 14, "cost": 118, "price": 145, "category": "Groceries"},
        {"id": "tea", "name": "Tea (250 g)", "quantity": 36, "cost": 54, "price": 70, "category": "Beverages"},
        {"id": "soap", "name": "Bathing soap", "quantity": 8, "cost": 26, "price": 35, "category": "Household"},
    ]

    return {
        "coconut": {
            "name": "Raju’s Coconut Cart", "category": "Street vendor", "products": coconuts,
            "sales": [[0, 0, 12], [0, 1, 8], [1, 0, 10], [1, 2, 16], [2, 0, 9], [2, 1, 7], [3, 0, 14], [4, 1, 10], [5, 0, 11], [6, 2, 20], [7, 0, 8], [8, 1, 9], [9, 0, 13]],
            "expenses": [[0, 180, "Fresh stock", "Stock"], [2, 80, "Cart and ice", "Supplies"], [5, 150, "Morning produce", "Stock"]],
        },
        "kirana": {
            "name": "Shanti General Store", "category": "Kirana store", "products": kirana,
            "sales": [[0, 0, 3], [0, 1, 2], [0, 3, 4], [1, 2, 2], [1, 4, 3], [2, 0, 5], [2, 3, 6], [3, 1, 4], [3, 2, 2], [4, 0, 3], [4, 4, 5], [5, 3, 7], [6, 1, 3], [7, 2, 4], [8, 0, 4], [9, 3, 8], [10, 4, 4], [11, 1, 5], [12, 2, 3], [13, 0, 6]],
            "expenses": [[0, 680, "Weekly supplier delivery", "Stock"], [1, 120, "Delivery and packing", "Supplies"], [3, 210, "Electricity bill", "Utilities"], [6, 450, "Staple restock", "Stock"], [10, 95, "Shop supplies", "Supplies"]],
        },
    }


def reset_demo_data(db):
    demo_ids = ("coconut", "kirana")
    demo_merchants = list(db.query(Merchant).filter(Merchant.id.in_(demo_ids), Merchant.is_demo.is_(True)))
    merchant_ids = [merchant.id for merchant in demo_merchants]
    if not merchant_ids:
        return
    for model in (
        RecommendationOutcome,
        BusinessInsight,
        AIRecommendation,
        ActionHistory,
        AutopilotTask,
        CampaignDraft,
        Scenario,
        InventoryRecord,
        Sale,
        Expense,
        Product,
    ):
        db.query(model).filter(model.merchant_id.in_(merchant_ids)).delete(synchronize_session=False)
    for merchant in demo_merchants:
        db.delete(merchant)
    db.flush()


def _seed_demo_extras(db, merchant_id):
    campaign_examples = {
        "coconut": {
            "id": "coconut-demo-campaign",
            "product_id": "coconut",
            "objective": "Introduce fresh coconuts to nearby customers",
            "offer": "",
            "copy_text": "Fresh coconuts are ready at Raju’s cart today. Stop by and ask about the selection.",
        },
        "kirana": {
            "id": "kirana-demo-campaign",
            "product_id": "tea",
            "objective": "Thank regular customers",
            "offer": "",
            "copy_text": "Thank you for shopping with Shanti General Store. Visit us for your everyday essentials.",
        },
    }
    task_examples = {
        "coconut": ("coconut-demo-task", "Count fresh stock before opening", "Check the shelf count before planning a purchase."),
        "kirana": ("kirana-demo-task", "Review tea and soap stock", "Compare counted stock with recent sales before reordering."),
    }
    campaign = campaign_examples[merchant_id]
    if db.get(CampaignDraft, campaign["id"]) is None:
        db.add(CampaignDraft(merchant_id=merchant_id, **campaign))

    task_id, title, goal = task_examples[merchant_id]
    if db.get(AutopilotTask, task_id) is None:
        db.add(AutopilotTask(
            id=task_id,
            merchant_id=merchant_id,
            title=title,
            goal=goal,
            status="proposed",
            requires_approval=True,
        ))
        db.flush()
        db.add(ActionHistory(
            merchant_id=merchant_id,
            task_id=task_id,
            action="proposed",
            details="Illustrative demo checklist; no external action was performed.",
        ))

    scenario_id = f"{merchant_id}-demo-scenario"
    if db.get(Scenario, scenario_id) is None:
        product = db.get(Product, "coconut" if merchant_id == "coconut" else "tea")
        values = ScenarioInput(
            available_inventory=product.quantity or 0,
            extra_stock=10,
            demand_per_day=8,
            period=1,
            price=product.price or 0,
            cost=product.cost or 0,
            discount=5,
        )
        result = simulate_scenario(values)
        db.add(Scenario(
            id=scenario_id,
            merchant_id=merchant_id,
            parameters=values.model_dump_json(),
            result=result.model_dump_json(),
        ))


def seed(reset_demo=False):
    with SessionLocal() as db:
        if reset_demo:
            reset_demo_data(db)
        for merchant_id, data in demo_data().items():
            merchant = db.get(Merchant, merchant_id)
            if merchant and not merchant.is_demo:
                continue
            if merchant is None:
                merchant = Merchant(id=merchant_id, name=data["name"], category=data["category"], is_demo=True)
                db.add(merchant)
                db.flush()
                for product in data["products"]:
                    db.add(Product(merchant_id=merchant_id, **product))
                db.flush()
                today = business_today()
                db.add_all([
                    Sale(
                        id=f"{merchant_id}-sale-{offset}-{product_index}",
                        merchant_id=merchant_id,
                        product_id=data["products"][product_index]["id"],
                        amount=quantity * data["products"][product_index]["price"],
                        date=today - timedelta(days=offset),
                        quantity=quantity,
                        unit_price=data["products"][product_index]["price"],
                        cost_of_goods=quantity * data["products"][product_index]["cost"],
                        note=f"{data['products'][product_index]['name']} · {quantity} sold",
                        source="demo",
                    )
                    for offset, product_index, quantity in data["sales"]
                ])
                db.add_all([
                    Expense(id=f"{merchant_id}-expense-{offset}", merchant_id=merchant_id, amount=amount,
                            date=today - timedelta(days=offset), note=note, category=category, source="demo")
                    for offset, amount, note, category in data["expenses"]
                ])
            _seed_demo_extras(db, merchant_id)
        if db.get(Merchant, "personal") is None:
            db.add(Merchant(id="personal", name="", category="", is_demo=False))
        db.commit()
        for merchant_id in ("coconut", "kirana"):
            merchant = db.get(Merchant, merchant_id)
            if merchant and merchant.is_demo:
                analyze_merchant(db, merchant_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize UdyamAI demo merchants.")
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="Replace only the seeded demo merchants and their records; personal data is preserved.",
    )
    args = parser.parse_args()
    seed(reset_demo=args.reset_demo)
    print("Initialized demo merchants, sample insights, a campaign draft, a scenario, and an action checklist.")
