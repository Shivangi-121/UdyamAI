from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.api import ScenarioInput
from app.services.calculations import simulate_scenario


def scenario(**changes):
    values = {
        "available_inventory": 10,
        "extra_stock": 5,
        "demand_per_day": 8,
        "period": 2,
        "price": Decimal("20.00"),
        "cost": Decimal("12.00"),
        "discount": Decimal("0"),
    }
    values.update(changes)
    return simulate_scenario(ScenarioInput(**values))


def test_zero_demand_and_zero_stock_produce_zero_sales():
    result = scenario(demand_per_day=0, available_inventory=0)
    assert result.baseline.units_sold == 0
    assert result.proposed.units_sold == 0
    assert result.proposed.revenue == Decimal("0.00")


def test_discount_changes_revenue_and_gross_profit_without_changing_demand():
    result = scenario(available_inventory=30, extra_stock=0, demand_per_day=4, period=1, discount=Decimal("25"))
    assert result.baseline.revenue == Decimal("80.00")
    assert result.proposed.revenue == Decimal("60.00")
    assert result.proposed.gross_profit == Decimal("12.00")


def test_insufficient_inventory_caps_units_sold():
    result = scenario(available_inventory=3, extra_stock=1, demand_per_day=20, period=2)
    assert result.baseline.units_sold == 3
    assert result.proposed.units_sold == 4
    assert result.proposed.unsold_units == 0
    assert result.proposed.gross_profit == Decimal("32.00")


@pytest.mark.parametrize("field,value", [("price", -1), ("cost", -1), ("period", 0), ("discount", 101), ("available_inventory", -1)])
def test_invalid_scenario_parameters_are_rejected(field, value):
    with pytest.raises(ValidationError):
        scenario(**{field: value})
