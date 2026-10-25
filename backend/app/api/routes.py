import hmac
import json
import time
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.agents import coordinate_recommendation
from app.db.session import get_db
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
from app.schemas.api import (
    AssistantRequest,
    AnalysisResult,
    BusinessInsightOut,
    CampaignCreate,
    CampaignGenerate,
    CampaignGenerated,
    CampaignOut,
    CampaignUpdate,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    HealthOut,
    InventoryUpdate,
    InventoryRisk,
    InsightStatus,
    MerchantOut,
    MerchantUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    Recommendation,
    OutcomeCreate,
    OutcomeOut,
    OutcomeUpdate,
    SaleCreate,
    SaleOut,
    SaleUpdate,
    ScenarioInput,
    ScenarioOut,
    ScenarioResult,
    SummaryOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services.assistant import answer_question, generate_campaign
from app.services.calculations import simulate_scenario
from app.services.intelligence import _inventory_risks, _serialize_insight, analyze_merchant

router = APIRouter(prefix="/api")
_assistant_requests: dict[str, deque[float]] = defaultdict(deque)


def authorized_merchant(
    merchant_id: str,
    authorization: str | None = Header(default=None),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    expected = get_settings().token_map.get(merchant_id)
    if get_settings().app_env.lower() == "production" and (not expected or expected.startswith("dev-")):
        raise HTTPException(status_code=503, detail="Production merchant credentials are not configured")
    if not expected or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Token is not authorized for this merchant")
    return merchant_id


def get_merchant(db: Session, merchant_id: str) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


def writable_merchant(db: Session, merchant_id: str) -> Merchant:
    merchant = get_merchant(db, merchant_id)
    if merchant.is_demo:
        raise HTTPException(status_code=403, detail="Demo merchant records are read-only")
    return merchant


def ensure_product(db: Session, merchant_id: str, product_id: str) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id, Product.merchant_id == merchant_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this merchant")
    return product


def rate_limit_assistant(merchant_id: str) -> None:
    now = time.monotonic()
    window = _assistant_requests[merchant_id]
    while window and window[0] <= now - 60:
        window.popleft()
    limit = get_settings().ai_requests_per_minute
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="Assistant request limit reached. Try again shortly.")
    window.append(now)


@router.get("/health", response_model=HealthOut)
def health():
    settings = get_settings()
    return {"status": "ok", "ai_mode": "live" if settings.llm_api_key and settings.llm_model else "demo"}


@router.get("/merchants/{merchant_id}", response_model=MerchantOut)
def read_merchant(
    merchant_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    return get_merchant(db, merchant_id)


@router.patch("/merchants/{merchant_id}", response_model=MerchantOut)
def update_merchant(
    merchant_id: str,
    payload: MerchantUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    merchant = writable_merchant(db, merchant_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide a name or category to update")
    if any(value is None for value in updates.values()):
        raise HTTPException(status_code=422, detail="Merchant fields cannot be null")
    for field, value in updates.items():
        setattr(merchant, field, value.strip() if field == "name" and value else value)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.get("/merchants/{merchant_id}/products", response_model=list[ProductOut])
def list_products(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    return list(db.scalars(select(Product).where(Product.merchant_id == merchant_id).order_by(Product.created_at)))


@router.post("/merchants/{merchant_id}/products", response_model=ProductOut, status_code=201)
def create_product(
    merchant_id: str,
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    product = Product(id=str(uuid4()), merchant_id=merchant_id, **payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/merchants/{merchant_id}/products/{product_id}", response_model=ProductOut)
def update_product(
    merchant_id: str,
    product_id: str,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    product = ensure_product(db, merchant_id, product_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one product field to update")
    if updates.get("name", "present") is None:
        raise HTTPException(status_code=422, detail="Product name cannot be null")
    for key, value in updates.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/merchants/{merchant_id}/products/{product_id}", status_code=204)
def delete_product(
    merchant_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    product = ensure_product(db, merchant_id, product_id)
    db.delete(product)
    db.commit()


@router.get("/merchants/{merchant_id}/sales", response_model=list[SaleOut])
def list_sales(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    return list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id).order_by(Sale.date.desc(), Sale.created_at.desc())))


@router.post("/merchants/{merchant_id}/sales", response_model=SaleOut, status_code=201)
def create_sale(
    merchant_id: str,
    payload: SaleCreate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    product = ensure_product(db, merchant_id, payload.product_id) if payload.product_id else None
    if payload.unit_price is not None:
        expected_amount = (payload.unit_price * payload.quantity).quantize(Decimal("0.01"))
        if payload.amount != expected_amount:
            raise HTTPException(status_code=422, detail="Sale amount must equal unit price multiplied by quantity")
    if product and product.quantity is not None and payload.quantity > product.quantity:
        raise HTTPException(status_code=409, detail="Sale quantity exceeds recorded stock")
    unit_price = payload.unit_price
    if product:
        if product.cost is not None:
            cogs = product.cost * payload.quantity
        else:
            cogs = None
        if product.quantity is not None:
            product.quantity -= payload.quantity
    else:
        cogs = None
    sale = Sale(
        id=str(uuid4()),
        merchant_id=merchant_id,
        cost_of_goods=cogs,
        source="user",
        **payload.model_dump(exclude={"unit_price"}),
        unit_price=unit_price,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale


@router.delete("/merchants/{merchant_id}/sales/{sale_id}", status_code=204)
def delete_sale(
    merchant_id: str,
    sale_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.merchant_id == merchant_id))
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.product_id:
        product = db.scalar(select(Product).where(Product.id == sale.product_id, Product.merchant_id == merchant_id))
        if product and product.quantity is not None:
            product.quantity += sale.quantity
    db.delete(sale)
    db.commit()


@router.patch("/merchants/{merchant_id}/sales/{sale_id}", response_model=SaleOut)
def update_sale(
    merchant_id: str,
    sale_id: str,
    payload: SaleUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.merchant_id == merchant_id))
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one sale field to update")
    if any(updates.get(field, "present") is None for field in ("amount", "date", "quantity", "note")):
        raise HTTPException(status_code=422, detail="Sale amount, date, quantity, and note cannot be null")

    old_product = ensure_product(db, merchant_id, sale.product_id) if sale.product_id else None
    new_product_id = updates.get("product_id", sale.product_id)
    new_product = ensure_product(db, merchant_id, new_product_id) if new_product_id else None
    new_quantity = updates.get("quantity", sale.quantity)
    new_amount = updates.get("amount", sale.amount)
    new_unit_price = updates.get("unit_price", sale.unit_price)
    if new_unit_price is not None and new_amount != (new_unit_price * new_quantity).quantize(Decimal("0.01")):
        raise HTTPException(status_code=422, detail="Sale amount must equal unit price multiplied by quantity")

    old_available = None
    if old_product and old_product.quantity is not None:
        old_available = old_product.quantity + sale.quantity
    if new_product and new_product.quantity is not None:
        available = old_available if new_product is old_product else new_product.quantity
        if available is not None and new_quantity > available:
            raise HTTPException(status_code=409, detail="Updated sale quantity exceeds recorded stock")

    if old_product and old_product.quantity is not None:
        old_product.quantity += sale.quantity
    if new_product and new_product.quantity is not None:
        new_product.quantity -= new_quantity
    for key, value in updates.items():
        setattr(sale, key, value)
    sale.cost_of_goods = new_product.cost * new_quantity if new_product and new_product.cost is not None else None
    db.commit()
    db.refresh(sale)
    return sale


@router.get("/merchants/{merchant_id}/expenses", response_model=list[ExpenseOut])
def list_expenses(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    return list(db.scalars(select(Expense).where(Expense.merchant_id == merchant_id).order_by(Expense.date.desc())))


@router.post("/merchants/{merchant_id}/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    merchant_id: str,
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    expense = Expense(id=str(uuid4()), merchant_id=merchant_id, source="user", **payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/merchants/{merchant_id}/expenses/{expense_id}", status_code=204)
def delete_expense(merchant_id: str, expense_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    writable_merchant(db, merchant_id)
    expense = db.scalar(select(Expense).where(Expense.id == expense_id, Expense.merchant_id == merchant_id))
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()


@router.patch("/merchants/{merchant_id}/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    merchant_id: str,
    expense_id: str,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    expense = db.scalar(select(Expense).where(Expense.id == expense_id, Expense.merchant_id == merchant_id))
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one expense field to update")
    if any(updates.get(field, "present") is None for field in ("amount", "date", "category", "note")):
        raise HTTPException(status_code=422, detail="Expense amount, date, category, and note cannot be null")
    for key, value in updates.items():
        setattr(expense, key, value)
    db.commit()
    db.refresh(expense)
    return expense

@router.post("/merchants/{merchant_id}/products/{product_id}/inventory", status_code=201)
def record_inventory(
    merchant_id: str,
    product_id: str,
    payload: InventoryUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    product = ensure_product(db, merchant_id, product_id)
    product.quantity = payload.quantity
    record = InventoryRecord(merchant_id=merchant_id, product_id=product_id, quantity=payload.quantity, note=payload.note)
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "product_id": product_id, "quantity": record.quantity, "recorded_at": record.recorded_at}


@router.get("/merchants/{merchant_id}/products/{product_id}/inventory")
def inventory_history(merchant_id: str, product_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    ensure_product(db, merchant_id, product_id)
    records = db.scalars(
        select(InventoryRecord)
        .where(InventoryRecord.merchant_id == merchant_id, InventoryRecord.product_id == product_id)
        .order_by(InventoryRecord.recorded_at.desc())
    )
    return [{"id": item.id, "quantity": item.quantity, "note": item.note, "recorded_at": item.recorded_at} for item in records]


@router.get("/merchants/{merchant_id}/summary", response_model=SummaryOut)
def summary(
    merchant_id: str,
    on: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    sales = list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id, Sale.date == on)))
    expenses = list(db.scalars(select(Expense).where(Expense.merchant_id == merchant_id, Expense.date == on)))
    revenue = sum((sale.amount for sale in sales), start=0)
    costs_known = bool(sales) and all(sale.cost_of_goods is not None for sale in sales)
    cogs = sum((sale.cost_of_goods for sale in sales if sale.cost_of_goods is not None), start=0)
    return SummaryOut(
        revenue=revenue,
        recorded_expenses=sum((expense.amount for expense in expenses), start=0),
        gross_profit=revenue - cogs if costs_known else None,
        gross_profit_available=costs_known,
        sales_count=len(sales),
        expenses_count=len(expenses),
        missing_information=[] if costs_known else ["Product cost is missing for one or more sales; gross profit is not shown."],
    )


@router.post("/merchants/{merchant_id}/intelligence/analyze", response_model=AnalysisResult)
def analyze_business(
    merchant_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    return analyze_merchant(db, merchant_id)


@router.get("/merchants/{merchant_id}/insights", response_model=list[BusinessInsightOut])
def list_insights(
    merchant_id: str,
    include_dismissed: bool = False,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    query = select(BusinessInsight).where(BusinessInsight.merchant_id == merchant_id)
    if not include_dismissed:
        query = query.where(
            BusinessInsight.status != "dismissed",
            (BusinessInsight.is_active.is_(True)) | (BusinessInsight.status == "saved"),
        )
    results = db.scalars(query.order_by(BusinessInsight.priority.desc(), BusinessInsight.generated_at.desc()).limit(50))
    return [_serialize_insight(item) for item in results]


@router.patch("/merchants/{merchant_id}/insights/{insight_id}", response_model=BusinessInsightOut)
def update_insight_status(
    merchant_id: str,
    insight_id: str,
    payload: InsightStatus,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    insight = db.scalar(select(BusinessInsight).where(
        BusinessInsight.id == insight_id,
        BusinessInsight.merchant_id == merchant_id,
    ))
    if insight is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    writable_merchant(db, merchant_id)
    insight.status = payload.status
    db.commit()
    db.refresh(insight)
    return _serialize_insight(insight)


@router.get("/merchants/{merchant_id}/inventory-risks", response_model=list[InventoryRisk])
def inventory_risks(
    merchant_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    products = list(db.scalars(select(Product).where(Product.merchant_id == merchant_id)))
    sales = list(db.scalars(select(Sale).where(Sale.merchant_id == merchant_id, Sale.date <= date.today())))
    return _inventory_risks(products, sales, date.today())


def _serialize_outcome(item: RecommendationOutcome) -> dict:
    return {
        "id": item.id,
        "merchant_id": item.merchant_id,
        "insight_id": item.insight_id,
        "recommendation": item.recommendation,
        "assumptions": json.loads(item.assumptions),
        "selected_action": item.selected_action,
        "baseline": json.loads(item.baseline),
        "observation_start": item.observation_start,
        "observation_end": item.observation_end,
        "actual_outcome": json.loads(item.actual_outcome) if item.actual_outcome else None,
        "fairly_comparable": item.fairly_comparable,
        "created_at": item.created_at,
    }


@router.get("/merchants/{merchant_id}/outcomes", response_model=list[OutcomeOut])
def list_outcomes(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    get_merchant(db, merchant_id)
    outcomes = db.scalars(
        select(RecommendationOutcome)
        .where(RecommendationOutcome.merchant_id == merchant_id)
        .order_by(RecommendationOutcome.created_at.desc())
    )
    return [_serialize_outcome(item) for item in outcomes]


@router.post("/merchants/{merchant_id}/outcomes", response_model=OutcomeOut, status_code=201)
def create_outcome(
    merchant_id: str,
    payload: OutcomeCreate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    if payload.insight_id and db.scalar(select(BusinessInsight.id).where(
        BusinessInsight.id == payload.insight_id,
        BusinessInsight.merchant_id == merchant_id,
    )) is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    outcome = RecommendationOutcome(
        id=str(uuid4()),
        merchant_id=merchant_id,
        insight_id=payload.insight_id,
        recommendation=payload.recommendation,
        assumptions=json.dumps(payload.assumptions),
        selected_action=payload.selected_action,
        baseline=json.dumps(payload.baseline, default=str),
        observation_start=payload.observation_start,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return _serialize_outcome(outcome)


@router.patch("/merchants/{merchant_id}/outcomes/{outcome_id}", response_model=OutcomeOut)
def update_outcome(
    merchant_id: str,
    outcome_id: str,
    payload: OutcomeUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    outcome = db.scalar(select(RecommendationOutcome).where(
        RecommendationOutcome.id == outcome_id,
        RecommendationOutcome.merchant_id == merchant_id,
    ))
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome record not found")
    if payload.observation_end < outcome.observation_start:
        raise HTTPException(status_code=422, detail="Observation end must not be before its start date")
    outcome.observation_end = payload.observation_end
    outcome.actual_outcome = json.dumps(payload.actual_outcome, default=str)
    outcome.fairly_comparable = payload.fairly_comparable
    db.commit()
    db.refresh(outcome)
    return _serialize_outcome(outcome)


@router.post("/merchants/{merchant_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(
    merchant_id: str,
    payload: ScenarioInput,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    result = simulate_scenario(payload)
    scenario = Scenario(id=str(uuid4()), merchant_id=merchant_id, parameters=payload.model_dump_json(), result=result.model_dump_json())
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.post("/merchants/{merchant_id}/scenarios/calculate", response_model=ScenarioResult)
def calculate_scenario(
    merchant_id: str,
    payload: ScenarioInput,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    return simulate_scenario(payload)


@router.get("/merchants/{merchant_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    get_merchant(db, merchant_id)
    return list(db.scalars(select(Scenario).where(Scenario.merchant_id == merchant_id).order_by(Scenario.created_at.desc())))


@router.delete("/merchants/{merchant_id}/scenarios/{scenario_id}", status_code=204)
def delete_scenario(merchant_id: str, scenario_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    scenario = db.scalar(select(Scenario).where(Scenario.id == scenario_id, Scenario.merchant_id == merchant_id))
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    writable_merchant(db, merchant_id)
    db.delete(scenario)
    db.commit()


@router.post("/merchants/{merchant_id}/assistant", response_model=Recommendation)
async def assistant(
    merchant_id: str,
    payload: AssistantRequest,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    rate_limit_assistant(merchant_id)
    recommendation = await answer_question(db, merchant_id, payload)
    db.add(AIRecommendation(
        id=str(uuid4()),
        merchant_id=merchant_id,
        title=recommendation.title,
        message=recommendation.message,
        evidence=json.dumps(recommendation.evidence),
        source=recommendation.source,
    ))
    db.commit()
    return recommendation


@router.post("/merchants/{merchant_id}/assistant/team", response_model=Recommendation)
def assistant_team(
    merchant_id: str,
    payload: AssistantRequest,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    return coordinate_recommendation(db, merchant_id, payload.question, payload.language)


@router.get("/merchants/{merchant_id}/recommendations")
def list_recommendations(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    get_merchant(db, merchant_id)
    recommendations = db.scalars(
        select(AIRecommendation)
        .where(AIRecommendation.merchant_id == merchant_id)
        .order_by(AIRecommendation.created_at.desc())
    )
    return [
        {
            "id": item.id,
            "title": item.title,
            "message": item.message,
            "evidence": json.loads(item.evidence),
            "source": item.source,
            "created_at": item.created_at,
        }
        for item in recommendations
    ]


@router.get("/merchants/{merchant_id}/campaigns", response_model=list[CampaignOut])
def list_campaigns(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    get_merchant(db, merchant_id)
    return list(db.scalars(select(CampaignDraft).where(CampaignDraft.merchant_id == merchant_id).order_by(CampaignDraft.created_at.desc())))


@router.post("/merchants/{merchant_id}/campaigns/generate", response_model=CampaignGenerated)
async def generate_campaign_copy(
    merchant_id: str,
    payload: CampaignGenerate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    get_merchant(db, merchant_id)
    rate_limit_assistant(merchant_id)
    return await generate_campaign(db, merchant_id, payload)


@router.post("/merchants/{merchant_id}/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(merchant_id: str, payload: CampaignCreate, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    writable_merchant(db, merchant_id)
    if payload.product_id:
        ensure_product(db, merchant_id, payload.product_id)
    campaign = CampaignDraft(id=str(uuid4()), merchant_id=merchant_id, **payload.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.patch("/merchants/{merchant_id}/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    merchant_id: str,
    campaign_id: str,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    campaign = db.scalar(select(CampaignDraft).where(CampaignDraft.id == campaign_id, CampaignDraft.merchant_id == merchant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign draft not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one campaign field to update")
    if any(updates.get(field, "present") is None for field in ("objective", "offer", "copy_text")):
        raise HTTPException(status_code=422, detail="Campaign objective, offer, and copy cannot be null")
    if updates.get("product_id"):
        ensure_product(db, merchant_id, updates["product_id"])
    for key, value in updates.items():
        setattr(campaign, key, value)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/merchants/{merchant_id}/campaigns/{campaign_id}", status_code=204)
def delete_campaign(merchant_id: str, campaign_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    writable_merchant(db, merchant_id)
    campaign = db.scalar(select(CampaignDraft).where(CampaignDraft.id == campaign_id, CampaignDraft.merchant_id == merchant_id))
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign draft not found")
    db.delete(campaign)
    db.commit()


@router.get("/merchants/{merchant_id}/tasks", response_model=list[TaskOut])
def list_tasks(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    get_merchant(db, merchant_id)
    return list(db.scalars(select(AutopilotTask).where(AutopilotTask.merchant_id == merchant_id).order_by(AutopilotTask.created_at.desc())))


@router.post("/merchants/{merchant_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(merchant_id: str, payload: TaskCreate, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    writable_merchant(db, merchant_id)
    task = AutopilotTask(id=str(uuid4()), merchant_id=merchant_id, title=payload.title, goal=payload.goal)
    db.add(task)
    db.flush()
    db.add(ActionHistory(merchant_id=merchant_id, task_id=task.id, action="proposed", details="Task proposed for merchant review."))
    db.commit()
    db.refresh(task)
    return task


@router.post("/merchants/{merchant_id}/tasks/plan", response_model=list[TaskOut], status_code=201)
def create_task_plan(merchant_id: str, payload: TaskCreate, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    writable_merchant(db, merchant_id)
    goal = payload.goal or payload.title
    titles = [f"Review the goal: {goal}", "Check stock and costs before acting", "Choose one next step"]
    tasks = [AutopilotTask(id=str(uuid4()), merchant_id=merchant_id, title=title, goal=payload.title) for title in titles]
    db.add_all(tasks)
    db.flush()
    db.add_all([ActionHistory(merchant_id=merchant_id, task_id=task.id, action="proposed", details="Task proposed for merchant review.") for task in tasks])
    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks


@router.patch("/merchants/{merchant_id}/tasks/{task_id}", response_model=TaskOut)
def update_task(
    merchant_id: str,
    task_id: str,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(authorized_merchant),
):
    writable_merchant(db, merchant_id)
    task = db.scalar(select(AutopilotTask).where(AutopilotTask.id == task_id, AutopilotTask.merchant_id == merchant_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Provide a task title or status to update")
    if "status" in updates and updates["status"] is None:
        raise HTTPException(status_code=422, detail="Task status cannot be null")
    if "title" in updates:
        if updates["title"] is None or not updates["title"].strip():
            raise HTTPException(status_code=422, detail="Task title cannot be empty")
        if task.status != "proposed":
            raise HTTPException(status_code=409, detail="Only proposed checklist items can be edited")
        task.title = updates["title"].strip()
    action = "edited"
    if "status" in updates:
        valid_transitions = {
            "proposed": {"approved", "rejected"},
            "approved": {"in_progress", "completed"},
            "in_progress": {"completed"},
            "rejected": set(),
            "completed": set(),
        }
        if updates["status"] not in valid_transitions[task.status]:
            raise HTTPException(status_code=409, detail=f"Cannot change task from {task.status} to {updates['status']}")
        task.status = updates["status"]
        action = updates["status"]
    db.add(ActionHistory(merchant_id=merchant_id, task_id=task.id, action=action, details="Checklist item updated; no external action was performed."))
    db.commit()
    db.refresh(task)
    return task


@router.get("/merchants/{merchant_id}/tasks/history")
def task_history(merchant_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    get_merchant(db, merchant_id)
    history = db.scalars(
        select(ActionHistory)
        .where(ActionHistory.merchant_id == merchant_id)
        .order_by(ActionHistory.created_at.desc(), ActionHistory.id.desc())
    )
    return [{"id": item.id, "task_id": item.task_id, "action": item.action, "details": item.details, "created_at": item.created_at} for item in history]


@router.delete("/merchants/{merchant_id}/tasks/{task_id}", status_code=204)
def delete_task(merchant_id: str, task_id: str, db: Session = Depends(get_db), _: str = Depends(authorized_merchant)):
    writable_merchant(db, merchant_id)
    task = db.scalar(select(AutopilotTask).where(AutopilotTask.id == task_id, AutopilotTask.merchant_id == merchant_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    db.add(ActionHistory(merchant_id=merchant_id, task_id=None, action="removed", details=f"Checklist item {task.title} was removed."))
    db.delete(task)
    db.commit()
