"""Price sensors submenu: import and export sources change independently."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.omnibattery.config_flow import (
    MarstekVenusConfigFlow,
    OptionsFlowHandler,
)

COMPONENT = Path(__file__).parent.parent / "custom_components" / "omnibattery"
LANGUAGES = ["ca", "de", "en", "es", "fr", "nl"]
NORDPOOL_STATE = SimpleNamespace(attributes={"raw_today": [{"value": 0.1}]})


def _options_flow(data: dict) -> OptionsFlowHandler:
    entry = SimpleNamespace(entry_id="test", data=data, options={})
    flow = OptionsFlowHandler(entry)
    flow.handler = "test"
    flow.hass = SimpleNamespace(
        states=SimpleNamespace(get=lambda _e: NORDPOOL_STATE),
        services=SimpleNamespace(has_service=lambda *_a: True),
        config_entries=SimpleNamespace(
            async_get_known_entry=lambda _id: entry,
            async_update_entry=lambda *_a, **_k: None,
            async_reload=AsyncMock(),
        ),
    )
    return flow


async def test_import_step_leaves_export_settings_untouched():
    flow = _options_flow(
        {"price_integration_type": "nordpool", "price_sensor": "sensor.old",
         "export_price_sensor": "sensor.export"}
    )

    await flow.async_step_price_import(
        {"price_integration_type": "nordpool", "price_sensor": "sensor.new"}
    )

    assert flow.config_data == {
        "price_integration_type": "nordpool",
        "price_sensor": "sensor.new",
    }


async def test_import_step_does_not_flip_the_predictive_mode():
    flow = _options_flow({"enable_predictive_charging": False})

    await flow.async_step_price_import(
        {"price_integration_type": "nordpool", "price_sensor": "sensor.new"}
    )

    assert "enable_predictive_charging" not in flow.config_data
    assert "predictive_charging_mode" not in flow.config_data


async def test_import_step_rejects_a_missing_sensor():
    flow = _options_flow({})

    result = await flow.async_step_price_import(
        {"price_integration_type": "nordpool"}
    )

    assert result["errors"] == {"price_sensor": "sensor_not_found"}


async def test_export_step_can_clear_the_export_sensor():
    flow = _options_flow(
        {"price_integration_type": "nordpool", "price_sensor": "sensor.import",
         "export_price_sensor": "sensor.export",
         "export_price_integration_type": "nordpool"}
    )

    await flow.async_step_price_export({})

    assert flow.config_data["export_price_sensor"] is None
    assert flow.config_data["export_price_integration_type"] is None
    assert "price_sensor" not in flow.config_data


async def test_export_step_validates_against_the_stored_import_provider():
    flow = _options_flow({"price_integration_type": "tibber"})

    result = await flow.async_step_price_export(
        {"export_price_sensor": "sensor.export"}
    )

    assert result["errors"] == {"export_price_integration_type": "export_type_required"}


async def test_setup_flow_chains_import_into_export():
    flow = MarstekVenusConfigFlow()
    flow.handler = "test"
    flow.hass = SimpleNamespace(
        states=SimpleNamespace(get=lambda _e: NORDPOOL_STATE),
        services=SimpleNamespace(has_service=lambda *_a: True),
        config_entries=SimpleNamespace(async_entries=lambda _d: []),
    )

    result = await flow.async_step_dynamic_pricing_config(
        {"price_integration_type": "nordpool", "price_sensor": "sensor.price"}
    )

    assert result["step_id"] == "price_export"
    assert flow.config_data["price_sensor"] == "sensor.price"
    assert "export_price_sensor" not in flow.config_data


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["strings.json"] + [f"translations/{l}.json" for l in LANGUAGES])
def test_new_steps_are_translated_with_short_explanations(name):
    data = _load(name)
    for flow_key in ("config", "options"):
        export = data[flow_key]["step"]["price_export"]
        assert set(export["data"]) == set(export["data_description"]) == {
            "export_price_sensor",
            "export_price_integration_type",
            "zonneplan_export_bonus_enabled",
        }
        # Two lines of a form field is roughly 200 characters.
        assert all(len(text) <= 200 for text in export["data_description"].values())
        assert not set(data[flow_key]["step"]["dynamic_pricing_config"]["data"]) & set(export["data"])
    options = data["options"]["step"]
    assert set(options["price_sensors"]["menu_options"]) == {"price_import", "price_export"}
    assert "price_sensors" in options["init"]["menu_options"]
    assert set(options["price_import"]["data"]) == {"price_integration_type", "price_sensor"}
