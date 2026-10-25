from datetime import date
import json


def test_health_reports_demo_mode_without_llm_credentials(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ai_mode"] == "demo"


def test_api_requires_auth_and_rejects_cross_merchant_token(client, auth):
    assert client.get("/api/merchants/personal").status_code == 401
    other = client.get("/api/merchants/personal", headers={"Authorization": "Bearer dev-coconut-token"})
    assert other.status_code == 403
    assert client.get("/api/merchants/personal", headers=auth).status_code == 200


def test_sales_validate_inventory_and_update_stock(client, auth):
    path = "/api/merchants/personal/sales"
    payload = {"product_id": "rice", "amount": "20.00", "date": date.today().isoformat(), "quantity": 2}
    created = client.post(path, json=payload, headers=auth)
    assert created.status_code == 201
    assert created.json()["cost_of_goods"] == "10.00"
    products = client.get("/api/merchants/personal/products", headers=auth).json()
    assert products[0]["quantity"] == 0
    too_many = client.post(path, json={**payload, "quantity": 1}, headers=auth)
    assert too_many.status_code == 409


def test_sale_edits_reconcile_stock_and_reject_invalid_quantities(client, auth):
    created = client.post(
        "/api/merchants/personal/sales",
        headers=auth,
        json={"product_id": "rice", "amount": "10", "unit_price": "10", "date": date.today().isoformat(), "quantity": 1},
    )
    sale_id = created.json()["id"]
    changed = client.patch(
        f"/api/merchants/personal/sales/{sale_id}",
        headers=auth,
        json={"amount": "20", "quantity": 2, "unit_price": "10"},
    )
    assert changed.status_code == 200
    assert changed.json()["cost_of_goods"] == "10.00"
    product = client.get("/api/merchants/personal/products", headers=auth).json()[0]
    assert product["quantity"] == 0
    invalid = client.patch(
        f"/api/merchants/personal/sales/{sale_id}",
        headers=auth,
        json={"quantity": 4, "amount": "40", "unit_price": "10"},
    )
    assert invalid.status_code == 409
    assert client.delete(f"/api/merchants/personal/sales/{sale_id}", headers=auth).status_code == 204
    product = client.get("/api/merchants/personal/products", headers=auth).json()[0]
    assert product["quantity"] == 2


def test_foreign_product_is_not_visible_or_sellable(client, auth):
    response = client.post(
        "/api/merchants/personal/sales",
        headers=auth,
        json={"product_id": "other-rice", "amount": "10", "date": date.today().isoformat(), "quantity": 1},
    )
    assert response.status_code == 404


def test_summary_does_not_label_revenue_less_expenses_as_profit(client, auth):
    client.post(
        "/api/merchants/personal/expenses",
        headers=auth,
        json={"amount": "5", "date": date.today().isoformat(), "category": "Other"},
    )
    response = client.get(f"/api/merchants/personal/summary?on={date.today().isoformat()}", headers=auth)
    assert response.status_code == 200
    assert response.json()["gross_profit"] is None
    assert response.json()["gross_profit_available"] is False


def test_business_twin_returns_and_persists_projection(client, auth):
    payload = {
        "available_inventory": 3, "extra_stock": 5, "demand_per_day": 8, "period": 1,
        "price": "20", "cost": "12", "discount": "10", "supplier_lead_time_days": 2,
    }
    response = client.post("/api/merchants/personal/scenarios", json=payload, headers=auth)
    assert response.status_code == 201
    result = json.loads(response.json()["result"])
    assert result["baseline"]["units_sold"] == 3
    assert result["proposed"]["gross_profit"] == "48.00"
    assert client.get("/api/merchants/personal/scenarios", headers=auth).status_code == 200


def test_campaign_and_task_lifecycle_are_persistent_and_audited(client, auth):
    campaign = client.post(
        "/api/merchants/personal/campaigns",
        json={"objective": "Weekend offer", "copy": "Come by this weekend"},
        headers=auth,
    )
    assert campaign.status_code == 201
    assert campaign.json()["copy"] == "Come by this weekend"

    task = client.post("/api/merchants/personal/tasks", json={"title": "Count stock"}, headers=auth)
    task_id = task.json()["id"]
    approved = client.patch(f"/api/merchants/personal/tasks/{task_id}", json={"status": "approved"}, headers=auth)
    assert approved.json()["status"] == "approved"
    assert client.get("/api/merchants/personal/tasks/history", headers=auth).json()[0]["action"] == "approved"
    rejected_transition = client.patch(
        f"/api/merchants/personal/tasks/{task_id}", json={"status": "proposed"}, headers=auth
    )
    assert rejected_transition.status_code == 409


def test_demo_merchants_are_read_only(client):
    response = client.post(
        "/api/merchants/coconut/products",
        headers={"Authorization": "Bearer dev-coconut-token"},
        json={"name": "Unexpected"},
    )
    assert response.status_code == 403


def test_assistant_returns_clear_demo_fallback_and_stores_recommendation(client, auth):
    response = client.post(
        "/api/merchants/personal/assistant",
        headers=auth,
        json={"question": "How much did I sell today?", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "demo"
    assert "demo mode" in response.json()["message"]
    history = client.get("/api/merchants/personal/recommendations", headers=auth)
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_campaign_generation_is_explicitly_labeled_demo_without_credentials(client, auth):
    response = client.post(
        "/api/merchants/personal/campaigns/generate",
        headers=auth,
        json={"objective": "Bring more people to my shop", "offer": "₹5 off", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "demo"
    assert "₹5 off" in response.json()["copy"]


def test_invalid_input_uses_standard_error_shape(client, auth):
    response = client.post(
        "/api/merchants/personal/expenses",
        headers=auth,
        json={"amount": "-1", "date": date.today().isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
