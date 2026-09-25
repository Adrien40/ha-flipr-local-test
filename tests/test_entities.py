"""Entities: sensors, alert thresholds, numbers, select, switch, button."""

from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.flipr_local.const import (
    BT_STATUS_OUT_OF_RANGE,
    BT_STATUS_PAUSED,
    BT_STATUS_WAITING,
    CONF_CHLORINE_MODEL,
    CONF_CYA,
    CONF_ORP_MAX,
    CONF_PH_MAX,
    CONF_PH_MIN,
    CONF_REFERENCE_TIME,
    CONF_SCAN_INTERVAL,
    CONF_TEMP_MAX,
)

from .conftest import entity_id, make_entry


async def _call(hass, domain, service, entity, **data):
    await hass.services.async_call(
        domain, service, {"entity_id": entity, **data}, blocking=True
    )
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Capteurs
# ---------------------------------------------------------------------------
async def test_measurement_sensors(hass, coordinator):
    def state(key):
        return hass.states.get(entity_id(hass, "sensor", key)).state

    assert float(state("temperature")) == pytest.approx(25.02)
    assert float(state("ph")) == pytest.approx(7.38, abs=0.02)
    assert float(state("orp")) == 700
    assert float(state("ph_raw")) == 1600
    assert float(state("orp_raw")) == 700.0
    assert float(state("battery")) == 3300
    assert float(state("battery_level")) == 73
    assert state("lsi_status") == "unknown"
    assert state("sync_mode") == "2"
    assert state("bluetooth_status") == "success"
    assert len(state("raw_frame")) == 26


async def test_sensor_shows_unknown_when_value_is_none(hass, coordinator):
    coordinator.update_volatile_state({"ph": None})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "sensor", "ph")).state == STATE_UNKNOWN


async def test_next_analysis_is_last_plus_interval(hass, coordinator):
    state = hass.states.get(entity_id(hass, "sensor", "next_analysis"))
    expected = coordinator.data["last_received"] + coordinator.update_interval
    assert dt_util.parse_datetime(state.state) == expected.replace(microsecond=0)


async def test_next_analysis_hidden_when_paused(hass, coordinator):
    coordinator.update_volatile_state({"active_measures": False})
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "sensor", "next_analysis")).state
        == STATE_UNKNOWN
    )


async def test_rssi_sensor_follows_advertisements(hass, coordinator, ble):
    state = hass.states.get(entity_id(hass, "sensor", "rssi"))
    assert state.state == str(ble.rssi)


# ---------------------------------------------------------------------------
# Alertes (seuils)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", ["ph_status", "orp_status", "temperature_status"])
async def test_alerts_off_when_values_in_range(hass, coordinator, key):
    assert hass.states.get(entity_id(hass, "binary_sensor", key)).state == STATE_OFF


async def test_ph_alert_follows_threshold_options(hass, coordinator, entry):
    ph_alert = entity_id(hass, "binary_sensor", "ph_status")
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_PH_MAX: 7.0, CONF_PH_MIN: 6.0}
    )
    await hass.async_block_till_done()
    assert hass.states.get(ph_alert).state == STATE_ON  # pH ≈ 7.38 > 7.0

    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_PH_MAX: 8.0}
    )
    await hass.async_block_till_done()
    assert hass.states.get(ph_alert).state == STATE_OFF


async def test_orp_and_temperature_alerts(hass, coordinator, entry):
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, CONF_ORP_MAX: 690, CONF_TEMP_MAX: 20.0},
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "orp_status")).state
        == STATE_ON
    )
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "temperature_status")).state
        == STATE_ON
    )


async def test_alert_boundary_values_are_in_range(hass, coordinator, entry):
    """The threshold itself is not an alert (strict comparisons)."""
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ORP_MAX: 700}
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "orp_status")).state
        == STATE_OFF
    )


async def test_alert_unknown_when_measurement_missing(hass, coordinator):
    coordinator.update_volatile_state({"ph": None})
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "ph_status")).state
        == STATE_UNKNOWN
    )


# ---------------------------------------------------------------------------
# Nombres : TAC / TH / TDS
# ---------------------------------------------------------------------------
async def test_water_parameters_drive_langelier(hass, coordinator):
    for key, value in (("tac", 100), ("th", 200), ("tds", 1000)):
        await _call(
            hass, "number", "set_value", entity_id(hass, "number", key), value=value
        )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()

    lsi = hass.states.get(entity_id(hass, "sensor", "lsi"))
    assert lsi.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    assert hass.states.get(entity_id(hass, "sensor", "lsi_status")).state in {
        "corrosive",
        "balanced",
        "scaling",
    }
    assert (
        float(hass.states.get(entity_id(hass, "sensor", "target_equilibrium_ph")).state)
        > 6
    )


@pytest.mark.parametrize(("key", "maximum"), [("tac", 500), ("th", 800), ("tds", 5000)])
async def test_water_parameter_bounds(hass, coordinator, key, maximum):
    entity = entity_id(hass, "number", key)
    await _call(hass, "number", "set_value", entity, value=maximum)
    assert float(hass.states.get(entity).state) == maximum
    with pytest.raises(ServiceValidationError):
        await _call(hass, "number", "set_value", entity, value=maximum + 1)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "number", "set_value", entity, value=-1)


async def test_water_parameters_are_persisted(hass, coordinator, hass_storage):
    await _call(
        hass, "number", "set_value", entity_id(hass, "number", "tac"), value=120
    )
    assert coordinator.data["tac"] == 120
    await coordinator.async_save_to_disk()
    assert hass_storage["flipr_local_aabbccddeeff"]["data"]["tac"] == 120


async def test_scan_interval_updates_coordinator(hass, coordinator):
    entity = entity_id(hass, "number", "scan_interval")
    await _call(hass, "number", "set_value", entity, value=30)
    assert coordinator.data[CONF_SCAN_INTERVAL] == 30
    assert coordinator.update_interval <= timedelta(minutes=30)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "number", "set_value", entity, value=4)  # minimum: 5 min


async def test_reference_time_entity(hass, coordinator):
    entity = entity_id(hass, "time", "reference_time")
    assert hass.states.get(entity).state == "08:00:00"
    await _call(hass, "time", "set_value", entity, time=time(6, 30).isoformat())
    assert coordinator.data[CONF_REFERENCE_TIME] == "06:30"
    assert hass.states.get(entity).state == "06:30:00"


# ---------------------------------------------------------------------------
# CyA and treatment type (kept)
# ---------------------------------------------------------------------------
async def test_cya_can_be_set(hass, coordinator):
    entity = entity_id(hass, "number", "cya")
    await _call(hass, "number", "set_value", entity, value=60)
    assert float(hass.states.get(entity).state) == 60
    assert coordinator.data["cya"] == 60


async def test_cya_is_unavailable_with_bromine(hass, coordinator):
    cya = entity_id(hass, "number", "cya")
    select = entity_id(hass, "select", "chlorine_model")
    assert hass.states.get(select).state == "chlorine"
    await _call(hass, "select", "select_option", select, option="bromine")
    assert hass.states.get(cya).state == STATE_UNAVAILABLE
    await _call(hass, "select", "select_option", select, option="chlorine")
    assert hass.states.get(cya).state != STATE_UNAVAILABLE


async def test_changing_treatment_does_not_revert_cya(hass, setup_integration):
    """Regression: the CyA entered on the entity was overwritten by the old
    options value whenever another setting (here, the treatment type) changed.

    The config flow writes `cya` into the options on creation: this reproduces
    that situation (CyA = 40 in the options).
    """
    entry = make_entry(**{CONF_CYA: 40})
    await setup_integration(entry)
    cya = entity_id(hass, "number", "cya")
    select = entity_id(hass, "select", "chlorine_model")
    await _call(hass, "number", "set_value", cya, value=80)

    await _call(hass, "select", "select_option", select, option="bromine")
    await _call(hass, "select", "select_option", select, option="chlorine")

    assert entry.options[CONF_CHLORINE_MODEL] == "chlorine"
    assert float(hass.states.get(cya).state) == 80


async def test_cya_option_change_is_applied(hass, coordinator, entry):
    """Changing CyA in the options form is still taken into account."""
    cya = entity_id(hass, "number", "cya")
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_CYA: 55}
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(cya).state) == 55


# ---------------------------------------------------------------------------
# "Automatic analysis" switch
# ---------------------------------------------------------------------------
async def test_switch_pauses_measurements(hass, coordinator):
    switch = entity_id(hass, "switch", "active_measures")
    assert hass.states.get(switch).state == STATE_ON
    await _call(hass, "switch", "turn_off", switch)
    assert hass.states.get(switch).state == STATE_OFF
    assert coordinator.data["bluetooth_status"] == BT_STATUS_PAUSED


async def test_switch_resume_requests_refresh(hass, coordinator):
    switch = entity_id(hass, "switch", "active_measures")
    await _call(hass, "switch", "turn_off", switch)
    coordinator.async_request_refresh = AsyncMock()
    await _call(hass, "switch", "turn_on", switch)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data["active_measures"] is True
    assert coordinator.data["bluetooth_status"] == BT_STATUS_WAITING
    coordinator.async_request_refresh.assert_awaited_once()


async def test_switch_resume_without_bluetooth_does_not_refresh(hass, coordinator, ble):
    switch = entity_id(hass, "switch", "active_measures")
    await _call(hass, "switch", "turn_off", switch)
    coordinator.async_request_refresh = AsyncMock()
    ble.scanner_count = 0
    await _call(hass, "switch", "turn_on", switch)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data["bluetooth_status"] == BT_STATUS_OUT_OF_RANGE
    coordinator.async_request_refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# "New analysis" button
# ---------------------------------------------------------------------------
async def test_button_requests_one_shot_analysis(hass, coordinator):
    button = entity_id(hass, "button", "force_analysis")
    coordinator.async_request_refresh = AsyncMock()
    await _call(hass, "button", "press", button)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator._force_one_shot is True
    coordinator.async_request_refresh.assert_awaited_once()
    assert coordinator.data["action_running"] is False  # reset to False at the end


async def test_button_ignored_while_analysis_running(hass, coordinator):
    coordinator.update_volatile_state({"action_running": True})
    coordinator.async_request_refresh = AsyncMock()
    await _call(hass, "button", "press", entity_id(hass, "button", "force_analysis"))
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator.async_request_refresh.assert_not_awaited()


async def test_button_is_not_blocked_when_out_of_range(hass, coordinator, ble):
    """Like Blue Connect: the button tries the analysis even without a recent advertisement."""
    ble.scanner_count = 0
    coordinator.async_request_refresh = AsyncMock()
    await _call(hass, "button", "press", entity_id(hass, "button", "force_analysis"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator._force_one_shot is True
    coordinator.async_request_refresh.assert_awaited_once()


async def test_button_swallows_refresh_errors(hass, coordinator):
    """An error during the analysis must not leave "action_running" stuck."""
    coordinator.async_request_refresh = AsyncMock(side_effect=RuntimeError("boom"))
    await _call(hass, "button", "press", entity_id(hass, "button", "force_analysis"))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data["action_running"] is False


async def test_raw_orp_is_not_affected_by_calibration_offset(hass, setup_integration):
    """Raw Redox is used to *establish* the offset: it must stay the probe's value."""
    entry = make_entry(**{"orp_calib": 640, "orp_ref": 650})
    await setup_integration(entry)
    raw = hass.states.get(entity_id(hass, "sensor", "orp_raw"))
    calibrated = hass.states.get(entity_id(hass, "sensor", "orp"))
    assert float(raw.state) == 700.0
    assert float(calibrated.state) == 710.0
    assert raw.attributes["unit_of_measurement"] == "mV"


async def test_raw_orp_is_a_diagnostic_entity(hass, coordinator):
    reg = er.async_get(hass).async_get(entity_id(hass, "sensor", "orp_raw"))
    assert reg.entity_category is EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    ("alert", "low_key", "high_key", "value"),
    [
        ("ph_status", "ph_min", "ph_max", 7.38),
        ("orp_status", "orp_min", "orp_max", 700),
        ("temperature_status", "temp_min", "temp_max", 25.02),
    ],
)
async def test_every_threshold_boundary(
    hass, coordinator, entry, alert, low_key, high_key, value
):
    """A measurement equal to a threshold is not an alert; just beyond it, it is."""
    measured = hass.states.get(
        entity_id(
            hass,
            "sensor",
            {
                "ph_status": "ph",
                "orp_status": "orp",
                "temperature_status": "temperature",
            }[alert],
        )
    ).state
    measured = float(measured)
    assert measured == pytest.approx(value, abs=0.02)
    entity = entity_id(hass, "binary_sensor", alert)
    step = 0.01 if alert != "orp_status" else 1
    wide = {
        "ph_min": 0,
        "ph_max": 14,
        "orp_min": 0,
        "orp_max": 1200,
        "temp_min": 0,
        "temp_max": 50,
    }

    for key, threshold, expected in (
        (low_key, measured, STATE_OFF),  # mesure == seuil bas
        (low_key, measured + step, STATE_ON),  # mesure < seuil bas
        (high_key, measured, STATE_OFF),  # mesure == seuil haut
        (high_key, measured - step, STATE_ON),  # mesure > seuil haut
    ):
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, **wide, key: threshold}
        )
        await hass.async_block_till_done()
        assert hass.states.get(entity).state == expected, (key, threshold)


# ---------------------------------------------------------------------------
# RSSI sensor out of range (like Blue Connect)
# ---------------------------------------------------------------------------
async def test_rssi_becomes_unavailable_as_soon_as_signal_is_lost(
    hass, coordinator, ble
):
    rssi = entity_id(hass, "sensor", "rssi")
    assert hass.states.get(rssi).state == str(ble.rssi)
    ble.last_seen_age = 500
    coordinator._on_ble_unavailable(None)
    await hass.async_block_till_done()
    assert hass.states.get(rssi).state == STATE_UNAVAILABLE


async def test_rssi_is_available_again_when_signal_returns(hass, coordinator, ble):
    rssi = entity_id(hass, "sensor", "rssi")
    ble.last_seen_age = 500
    coordinator._on_ble_unavailable(None)
    await hass.async_block_till_done()
    ble.last_seen_age = 0
    coordinator._on_ble_seen(None, None)
    await hass.async_block_till_done()
    assert hass.states.get(rssi).state == str(ble.rssi)


async def test_rssi_unavailable_when_signal_disappears_between_polls(
    hass, coordinator, ble
):
    """Even without a loss callback, a scheduled cycle notices the absence and updates."""
    rssi = entity_id(hass, "sensor", "rssi")
    ble.last_seen_age = 500
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(rssi).state == STATE_UNAVAILABLE
