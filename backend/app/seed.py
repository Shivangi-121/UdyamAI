from datetime import date, timedelta

from app.db.session import SessionLocal
from app.models import Expense, Merchant, Product, Sale


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


def seed():
    with SessionLocal() as db:
        for merchant_id, data in demo_data().items():
            if db.get(Merchant, merchant_id):
                continue
            merchant = Merchant(id=merchant_id, name=data["name"], category=data["category"], is_demo=True)
            db.add(merchant)
            for product in data["products"]:
                db.add(Product(merchant_id=merchant_id, **product))
            today = date.today()
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
        if db.get(Merchant, "personal") is None:
            db.add(Merchant(id="personal", name="", category="", is_demo=False))
        db.commit()


if __name__ == "__main__":
    seed()
    print("Seeded demo merchants and an empty personal merchant.")
