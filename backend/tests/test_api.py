from datetime import date, timedelta
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
    edited = client.patch(
        f"/api/merchants/personal/tasks/{task_id}",
        json={"title": "Count and verify stock"},
        headers=auth,
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Count and verify stock"
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


def test_new_merchant_gets_no_fabricated_trends(client, auth):
    result = client.post("/api/merchants/personal/intelligence/analyze", headers=auth)
    assert result.status_code == 200
    body = result.json()
    assert body["maturity"] == "new"
    assert body["insights"] == []
    assert body["inventory_risks"][0]["risk"] == "unknown"
    assert body["missing_information"]


def test_sales_trend_is_evidence_based_deduplicated_and_dismissible(client, auth):
    today = date.today()
    for days_ago, amount in [(0, 100), (2, 100), (4, 100), (7, 50), (9, 50), (11, 50)]:
        response = client.post(
            "/api/merchants/personal/sales",
            headers=auth,
            json={"amount": str(amount), "date": (today - timedelta(days=days_ago)).isoformat()},
        )
        assert response.status_code == 201

    path = "/api/merchants/personal/intelligence/analyze"
    first = client.post(path, headers=auth).json()
    second = client.post(path, headers=auth).json()
    trends = [item for item in first["insights"] if item["kind"] == "sales_trend"]
    assert len(trends) == 1
    assert "increased" in trends[0]["headline"]
    assert len([item for item in second["insights"] if item["kind"] == "sales_trend"]) == 1
    assert len(client.get("/api/merchants/personal/insights", headers=auth).json()) == 1

    saved = client.patch(
        f"/api/merchants/personal/insights/{trends[0]['id']}",
        headers=auth,
        json={"status": "saved"},
    )
    assert saved.status_code == 200
    rechecked = client.post(path, headers=auth).json()
    assert any(item["id"] == trends[0]["id"] and item["status"] == "saved" for item in rechecked["insights"])

    dismissed = client.patch(
        f"/api/merchants/personal/insights/{trends[0]['id']}",
        headers=auth,
        json={"status": "dismissed"},
    )
    assert dismissed.status_code == 200
    assert client.get("/api/merchants/personal/insights", headers=auth).json() == []


def test_stock_risk_requires_sales_and_stock_and_estimates_replenishment(client, auth):
    today = date.today()
    product_path = "/api/merchants/personal/products/rice"
    assert client.patch(product_path, headers=auth, json={"supplier_lead_time_days": 3}).status_code == 200
    assert client.post(
        "/api/merchants/personal/products/rice/inventory",
        headers=auth,
        json={"quantity": 100},
    ).status_code == 201
    for days_ago in (5, 4, 3):
        created = client.post(
            "/api/merchants/personal/sales",
            headers=auth,
            json={
                "product_id": "rice",
                "amount": "100",
                "quantity": 10,
                "date": (today - timedelta(days=days_ago)).isoformat(),
            },
        )
        assert created.status_code == 201
    client.post(
        "/api/merchants/personal/products/rice/inventory",
        headers=auth,
        json={"quantity": 2},
    )
    risks = client.get("/api/merchants/personal/inventory-risks", headers=auth)
    rice = risks.json()[0]
    assert rice["risk"] == "high"
    assert rice["estimated_days_remaining"] == "2.00"
    assert rice["suggested_replenishment"] == 4

    analysis = client.post("/api/merchants/personal/intelligence/analyze", headers=auth).json()
    stock_alerts = [item for item in analysis["insights"] if item["kind"] == "inventory_risk"]
    assert len(stock_alerts) == 1
    assert stock_alerts[0]["entity_id"] == "rice"


def test_low_margin_insight_uses_only_recorded_units_and_entered_cost(client, auth):
    today = date.today()
    client.post(
        "/api/merchants/personal/products/rice/inventory",
        headers=auth,
        json={"quantity": 100},
    )
    for days_ago in (5, 4, 3):
        response = client.post(
            "/api/merchants/personal/sales",
            headers=auth,
            json={
                "product_id": "rice",
                "amount": "51",
                "quantity": 10,
                "date": (today - timedelta(days=days_ago)).isoformat(),
            },
        )
        assert response.status_code == 201
    analysis = client.post("/api/merchants/personal/intelligence/analyze", headers=auth).json()
    margins = [item for item in analysis["insights"] if item["kind"] == "low_margin"]
    assert len(margins) == 1
    assert margins[0]["entity_id"] == "rice"
    assert "2.0%" in margins[0]["observed"]
    assert "net profit" in margins[0]["why_it_matters"]


def test_recommendation_outcome_can_be_recorded_without_claiming_causation(client, auth):
    analyzed = client.post("/api/merchants/personal/intelligence/analyze", headers=auth).json()
    insight_id = None
    if analyzed["insights"]:
        insight_id = analyzed["insights"][0]["id"]
    created = client.post(
        "/api/merchants/personal/outcomes",
        headers=auth,
        json={
            "insight_id": insight_id,
            "recommendation": "Review sales",
            "assumptions": ["Recorded entries are complete"],
            "selected_action": "Check the notebook",
            "baseline": {"recorded_sales": 100},
            "observation_start": date.today().isoformat(),
        },
    )
    assert created.status_code == 201
    updated = client.patch(
        f"/api/merchants/personal/outcomes/{created.json()['id']}",
        headers=auth,
        json={
            "observation_end": date.today().isoformat(),
            "actual_outcome": {"recorded_sales": 120},
            "fairly_comparable": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["fairly_comparable"] is False
    assert client.get("/api/merchants/personal/outcomes", headers=auth).json()[0]["actual_outcome"]["recorded_sales"] == 120
