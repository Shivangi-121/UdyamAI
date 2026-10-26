from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator

DateValue = date


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MerchantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=100)


class MerchantOut(ORMModel):
    id: str
    name: str
    category: str
    is_demo: bool
    created_at: datetime


class AccountRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(default="", max_length=120)
    business_name: str = Field(default="", max_length=160)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class AccountLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class PasswordResetRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class PasswordResetComplete(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=128)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=120)
    business_name: str | None = Field(default=None, max_length=160)
    business_category: str | None = Field(default=None, max_length=100)
    business_model: Literal["products", "services", "both"] | None = None
    sales_channels: list[Literal["online", "offline"]] | None = Field(default=None, max_length=2)
    business_stage: Literal["starting", "operating", "established"] | None = None
    sales_tracking: Literal["memory", "notebook", "digital", "starting"] | None = None
    business_size: Literal["solo", "2-5", "6-20", "21+"] | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    business_location: str | None = Field(default=None, max_length=120)
    goals: list[Literal[
        "sales", "margins", "expenses", "inventory", "customers", "marketing", "performance", "automation"
    ]] | None = Field(default=None, max_length=8)
    preferred_language: Literal["en", "hi", "hinglish"] | None = None
    response_detail: Literal["simple", "balanced", "detailed"] | None = None
    interaction_mode: Literal["text", "voice", "both"] | None = None
    theme: Literal["system", "light", "dark"] | None = None
    notifications: dict[str, bool] | None = None
    onboarding_step: int | None = Field(default=None, ge=0, le=8)
    onboarding_answers: dict[str, str | list[str]] | None = None
    onboarding_completed: bool | None = None

    @field_validator("sales_channels", "goals")
    @classmethod
    def reject_duplicates(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Duplicate values are not allowed")
        return value

    @field_validator("notifications")
    @classmethod
    def validate_notifications(cls, value):
        if value is not None and not set(value).issubset({"business_insights", "product_updates"}):
            raise ValueError("Unsupported notification preference")
        return value

    @field_validator("onboarding_answers")
    @classmethod
    def validate_onboarding_answers(cls, value):
        allowed = {
            "business", "businessName", "businessModel", "channels", "stage", "tracking", "goals", "next", "products",
            "preferredLanguage", "responseDetail", "theme", "interactionMode", "currency",
        }
        if value is not None and not set(value).issubset(allowed):
            raise ValueError("Unsupported onboarding answer")
        return value


class ProfileOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    merchant_id: str
    business_name: str
    business_category: str
    business_model: str | None
    sales_channels: list[str]
    business_stage: str | None
    sales_tracking: str | None
    business_size: str | None
    currency: str
    business_location: str | None
    goals: list[str]
    preferred_language: str
    response_detail: str
    interaction_mode: str
    theme: str
    notifications: dict[str, bool]
    onboarding_step: int
    onboarding_answers: dict[str, Any]
    onboarding_completed: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    profile: ProfileOut


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=100)
    quantity: int | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    supplier_lead_time_days: int | None = Field(default=None, ge=0, le=365)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=100)
    quantity: int | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    supplier_lead_time_days: int | None = Field(default=None, ge=0, le=365)


class ProductOut(ProductCreate, ORMModel):
    id: str
    merchant_id: str
    created_at: datetime


class SaleCreate(BaseModel):
    product_id: str | None = None
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    date: date
    quantity: int = Field(default=1, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    note: str = Field(default="", max_length=500)


class SaleUpdate(BaseModel):
    product_id: str | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    date: DateValue | None = None
    quantity: int | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


class SaleOut(ORMModel):
    id: str
    merchant_id: str
    product_id: str | None
    amount: Decimal
    date: date
    quantity: int
    unit_price: Decimal | None
    cost_of_goods: Decimal | None
    note: str
    source: str
    created_at: datetime


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    date: date
    category: str = Field(default="Other", min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)


class ExpenseUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    date: DateValue | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ExpenseOut(ORMModel):
    id: str
    merchant_id: str
    amount: Decimal
    date: date
    category: str
    note: str
    source: str
    created_at: datetime


class InventoryUpdate(BaseModel):
    quantity: int = Field(ge=0)
    note: str = Field(default="", max_length=250)


class ScenarioInput(BaseModel):
    available_inventory: int = Field(ge=0)
    extra_stock: int = Field(ge=0)
    demand_per_day: int = Field(ge=0)
    period: int = Field(ge=1, le=90)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    discount: Decimal = Field(default=0, ge=0, le=100, max_digits=5, decimal_places=2)
    supplier_lead_time_days: int | None = Field(default=None, ge=0, le=365)


class Projection(BaseModel):
    inventory: int
    demand: int
    units_sold: int
    revenue: Decimal
    cost_of_goods_sold: Decimal
    gross_profit: Decimal
    unsold_units: int


class ScenarioResult(BaseModel):
    baseline: Projection
    proposed: Projection
    differences: dict[str, Decimal | int]
    assumptions: list[str]
    limitations: list[str]


class ScenarioOut(ORMModel):
    id: str
    merchant_id: str
    parameters: str
    result: str
    created_at: datetime


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    language: Literal["en", "hi"] = "en"
    context: list[ConversationTurn] = Field(default_factory=list, max_length=8)


class Recommendation(BaseModel):
    title: str
    message: str
    evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    next_action: str
    source: Literal["llm", "demo", "rules"] = "demo"
    observed_data: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class VoiceConversationOut(BaseModel):
    transcript: str = Field(min_length=1, max_length=2000)
    transcript_language: str | None = None
    response: Recommendation
    speech_audio: str | None = None
    speech_content_type: str | None = None
    speech_error: str | None = None


class CampaignCreate(BaseModel):
    product_id: str | None = None
    objective: str = Field(min_length=2, max_length=250)
    offer: str = Field(default="", max_length=250)
    copy_text: str = Field(default="", max_length=4000, validation_alias=AliasChoices("copy_text", "copy"), serialization_alias="copy")
    status: Literal["draft"] = "draft"


class CampaignUpdate(BaseModel):
    product_id: str | None = None
    objective: str | None = Field(default=None, min_length=2, max_length=250)
    offer: str | None = Field(default=None, max_length=250)
    copy_text: str | None = Field(default=None, max_length=4000, validation_alias=AliasChoices("copy_text", "copy"), serialization_alias="copy")


class CampaignOut(ORMModel):
    id: str
    merchant_id: str
    product_id: str | None
    objective: str
    offer: str
    copy_text: str = Field(validation_alias="copy_text", serialization_alias="copy")
    status: str
    created_at: datetime
    updated_at: datetime


class CampaignGenerate(BaseModel):
    product_id: str | None = None
    objective: str = Field(min_length=2, max_length=250)
    offer: str = Field(default="", max_length=250)
    language: Literal["en", "hi"] = "en"
    tone: str = Field(default="friendly", max_length=60)


class CampaignGenerated(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    copy_text: str = Field(validation_alias=AliasChoices("copy_text", "copy"), serialization_alias="copy")
    source: Literal["llm", "demo"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    goal: str = Field(default="", max_length=500)


class TaskStatus(BaseModel):
    status: Literal["proposed", "approved", "rejected", "in_progress", "completed"]


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    status: Literal["proposed", "approved", "rejected", "in_progress", "completed"] | None = None


class TaskOut(ORMModel):
    id: str
    merchant_id: str
    title: str
    goal: str
    status: str
    requires_approval: bool
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    ai_mode: Literal["live", "demo"]


class APIError(BaseModel):
    error: str
    message: str


class SummaryOut(BaseModel):
    revenue: Decimal
    recorded_expenses: Decimal
    gross_profit: Decimal | None
    gross_profit_available: bool
    sales_count: int
    expenses_count: int
    missing_information: list[str]


class BusinessInsightOut(ORMModel):
    id: str
    merchant_id: str
    kind: str
    entity_id: str | None
    priority: int
    headline: str
    observed: str
    evidence: list[str]
    comparison_period: str
    why_it_matters: str
    next_action: str
    confidence: str
    data_quality: str
    status: str
    is_active: bool
    generated_at: datetime
    evaluated_at: datetime


class InsightStatus(BaseModel):
    status: Literal["unread", "read", "saved", "dismissed"]


class InventoryRisk(BaseModel):
    product_id: str
    product_name: str
    available_stock: int | None
    units_sold: int
    sales_days: int
    recent_daily_rate: Decimal | None
    estimated_days_remaining: Decimal | None
    supplier_lead_time_days: int | None
    risk: Literal["unknown", "low", "watch", "high"]
    suggested_replenishment: int | None
    assumptions: list[str]


class AnalysisResult(BaseModel):
    generated_at: datetime
    maturity: Literal["new", "emerging", "established"]
    insights: list[BusinessInsightOut]
    inventory_risks: list[InventoryRisk]
    missing_information: list[str]
    source: Literal["recorded_data", "demo_data"]


class OutcomeCreate(BaseModel):
    insight_id: str | None = None
    recommendation: str = Field(min_length=2, max_length=250)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    selected_action: str = Field(min_length=2, max_length=500)
    baseline: dict[str, str | int | Decimal | None] = Field(default_factory=dict)
    observation_start: date


class OutcomeUpdate(BaseModel):
    observation_end: date
    actual_outcome: dict[str, str | int | Decimal | None]
    fairly_comparable: bool


class OutcomeOut(ORMModel):
    id: str
    merchant_id: str
    insight_id: str | None
    recommendation: str
    assumptions: list[str]
    selected_action: str
    baseline: dict[str, str | int | Decimal | None]
    observation_start: date
    observation_end: date | None
    actual_outcome: dict[str, str | int | Decimal | None] | None
    fairly_comparable: bool | None
    created_at: datetime
