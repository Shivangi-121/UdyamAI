import json
import re
from datetime import date
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import coordinate_recommendation
from app.core.config import get_settings
from app.models import Expense, Merchant, Product, Sale
from app.schemas.api import AssistantRequest, CampaignGenerate, CampaignGenerated, Recommendation
from app.services.calculations import recorded_metrics


def merchant_context(db: Session, merchant_id: str) -> dict:
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    products = list(db.scalars(select(Product).where(Product.merchant_id == merchant_id)))
    sales = list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id).order_by(Sale.date.desc(), Sale.created_at.desc())))
    expenses = list(db.scalars(select(Expense).where(Expense.merchant_id == merchant_id).order_by(Expense.date.desc(), Expense.created_at.desc())))
    return {
        "merchant": {"name": merchant.name, "category": merchant.category},
        "products": [
            {"id": p.id, "name": p.name, "stock": p.quantity, "unit_cost": str(p.cost) if p.cost is not None else None, "price": str(p.price) if p.price is not None else None}
            for p in products
        ],
        "sales": [
            {"date": s.date.isoformat(), "amount": str(s.amount), "quantity": s.quantity, "product_id": s.product_id, "cost_of_goods": str(s.cost_of_goods) if s.cost_of_goods is not None else None}
            for s in sales[:200]
        ],
        "expenses": [{"date": e.date.isoformat(), "amount": str(e.amount), "category": e.category} for e in expenses[:100]],
        "recorded_metrics": recorded_metrics(sales, expenses),
    }


async def answer_question(db: Session, merchant_id: str, request: AssistantRequest) -> Recommendation:
    settings = get_settings()
    context = merchant_context(db, merchant_id)
    if not settings.llm_api_key or not settings.llm_model:
        result = demo_answer(db, merchant_id, request)
        result.message = f"{result.message} AI is in demo mode because an LLM key/model is not configured."
        return result

    system_prompt = (
        "You are UdyamAI, a helpful small-business assistant. Use only the supplied merchant records. "
        "Never invent metrics or present gross profit as net profit. State when information is missing. "
        "For calculations, explain but do not alter supplied deterministic results. Do not perform actions. "
        "Return only a JSON object with title, message, evidence (array), missing_information (array), "
        "next_action, observed_data (array), assumptions (array)."
    )
    body = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"question": request.question, "language": request.language, "merchant_data": context}, ensure_ascii=False)},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json=body,
            )
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="AI provider is rate-limiting requests. Try again shortly.")
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(raw)
        payload["source"] = "llm"
        return Recommendation.model_validate(payload)
    except HTTPException:
        raise
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable. Please retry.") from exc
    except (httpx.HTTPStatusError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="AI service returned an invalid response.") from exc


async def generate_campaign(db: Session, merchant_id: str, request: CampaignGenerate) -> CampaignGenerated:
    settings = get_settings()
    context = merchant_context(db, merchant_id)
    product = None
    if request.product_id:
        product = next((item for item in context["products"] if item["id"] == request.product_id), None)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found for this merchant")
    if not settings.llm_api_key or not settings.llm_model:
        product_name = product["name"] if product else "your shop"
        offer_line = f"Offer: {request.offer}. " if request.offer else ""
        copy = (
            f"At {product_name}: {request.objective}. {offer_line}Visit us and ask in store for details."
            if request.language == "en"
            else f"{product_name}: {request.objective}। {f'ऑफ़र: {request.offer}। ' if request.offer else ''}जानकारी के लिए दुकान पर पूछें।"
        )
        return CampaignGenerated(copy_text=copy[:1500], source="demo")

    instruction = (
        "Write one short editable small-business promotion. Use only product information supplied. "
        "Do not invent discounts, availability, urgency, customer data, or claims. Do not send it. "
        "Return only the promotional copy, without quotation marks."
    )
    prompt = {
        "objective": request.objective,
        "offer": request.offer,
        "language": request.language,
        "tone": request.tone,
        "product": product,
        "merchant": context["merchant"],
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "temperature": 0.4,
                    "max_tokens": 220,
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                },
            )
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="AI provider is rate-limiting requests. Try again shortly.")
        response.raise_for_status()
        copy = response.json()["choices"][0]["message"]["content"].strip()
        if not copy or len(copy) > 4000:
            raise ValueError("Invalid campaign copy")
        return CampaignGenerated(copy_text=copy, source="llm")
    except HTTPException:
        raise
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable. Please retry.") from exc
    except (httpx.HTTPStatusError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="AI service returned an invalid response.") from exc


def demo_answer(db: Session, merchant_id: str, request: AssistantRequest) -> Recommendation:
    context = merchant_context(db, merchant_id)
    question = request.question.casefold()
    products = list(db.scalars(select(Product).where(Product.merchant_id == merchant_id)))
    sales = list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id)))
    today_sales = [sale for sale in sales if sale.date == date.today()]
    evidence = []
    missing = []
    title = "A practical next step"
    next_action = "Check your stock"
    if re.search(r"earn|sell|sales|sale|kamai|bikri|बिक्री|कमाई", question):
        title = "Today’s recorded sales" if request.language == "en" else "आज की दर्ज बिक्री"
        amount = sum((sale.amount for sale in today_sales), Decimal("0"))
        message = (
            f"{len(today_sales)} sale(s) totaling ₹{amount:.2f} are recorded for today."
            if today_sales
            else "No sales have been recorded today yet. You can enter a total amount to get started."
        )
        evidence.append(f"Recorded for {date.today().isoformat()}: {len(today_sales)} sale(s), ₹{amount:.2f} revenue.")
        costs_known = bool(today_sales) and all(sale.cost_of_goods is not None for sale in today_sales)
        if costs_known:
            cogs = sum((sale.cost_of_goods for sale in today_sales), Decimal("0"))
            evidence.append(f"Recorded gross profit before other expenses: ₹{amount - cogs:.2f}.")
        elif today_sales:
            missing.append("Unit cost is missing for one or more sales; gross profit is not shown.")
        next_action = "Record another sale" if not today_sales else "Review business insights"
    elif re.search(r"product|sell the most|top item|popular|sabse|zyada|उत्पाद|ज़्यादा", question):
        quantities: dict[str, int] = {}
        for sale in sales:
            if sale.product_id:
                quantities[sale.product_id] = quantities.get(sale.product_id, 0) + sale.quantity
        ranked = sorted(
            ((product, quantities.get(product.id, 0)) for product in products),
            key=lambda item: item[1],
            reverse=True,
        )
        title = "Products with the most recorded sales"
        if ranked and ranked[0][1]:
            product, quantity = ranked[0]
            message = f"{product.name} has the most recorded units sold: {quantity}. This is based on all sales currently recorded."
            evidence.append(f"{product.name}: {quantity} recorded units sold.")
        else:
            message = "There are not enough product-linked sales to rank products. Record sales against products to build a comparison."
            missing.append("No product-linked sales are available.")
        next_action = "Record a product sale"
    elif re.search(r"stock|order|buy|replenish|inventory|mangw|स्टॉक|खरीद", question):
        counted = sorted((product for product in products if product.quantity is not None), key=lambda item: item.quantity or 0)
        uncounted = [product.name for product in products if product.quantity is None]
        title = "A stock check to start with"
        if counted:
            product = counted[0]
            message = f"{product.name} has the lowest recorded stock at {product.quantity}. There is not enough demand history here to recommend a reliable order quantity."
            evidence.append(f"Lowest counted stock: {product.name} · {product.quantity} units.")
        else:
            message = "There is no counted stock yet. Add a product and record its shelf quantity before planning a reorder."
            missing.append("No product stock counts are available.")
        if uncounted:
            missing.append(f"Stock count is missing for {', '.join(uncounted[:5])}.")
        next_action = "Count my stock"
    elif re.search(r"campaign|offer|diwali|promotion|marketing|ऑफ़र|ऑफर", question):
        title = "Draft a promotion"
        message = "I can help prepare editable promotional copy. Choose the product and offer details; the draft will not be sent."
        next_action = "Open campaign studio"
    else:
        summary = context["recorded_metrics"]
        title = "A careful business check-in"
        message = "I can use your saved records, but I need a specific question to give a useful answer. You can ask about today’s sales, stock, product sales, or a promotion."
        evidence.extend([
            f"{summary['sales_count']} recorded sales; revenue ₹{summary['revenue']}.",
            f"{len(products)} products on the list.",
        ])
        if not summary["gross_profit_available"]:
            missing.extend(summary["missing_information"])
        next_action = "Ask about your stock"
    if request.language == "hi":
        title = f"उद्यमAI: {title}"
    return Recommendation(
        title=title,
        message=message,
        evidence=evidence,
        missing_information=missing,
        next_action=next_action,
        source="demo",
        observed_data=[],
        assumptions=["Only records saved for this merchant were used."],
    )
