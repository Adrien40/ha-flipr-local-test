# Changelog

## 1.2.1

### Fixed
- `start_notify`, `stop_notify`, `disconnect` and the direct read used by
  "Flipr Start Max" had no timeout: an unresponsive BLE stack after a
  successful connection could block the update cycle indefinitely. All four
  are now bounded by the new `TIMEOUT_GATT_OP` (10s), matching Blue Connect
  Local.
- The notification queue overflow handler wrapped the wrong call:
  `call_soon_threadsafe` was inside the `try`, but it never raises
  `QueueFull` itself (it only schedules `put_nowait`, which runs later,
  outside the `try`). A burst of notifications overflowing the queue
  therefore surfaced as an unhandled "Error doing job" exception instead of
  the intended clean debug log. Fixed by moving the `try`/`except` to where
  `put_nowait` actually runs, matching the pattern already used by Blue
  Connect Local.

### Added
- Scheduled analyses are now aligned on slots (interval + reference time),
  matching Blue Connect Local, instead of a flat rolling interval. New
  **Reference Time** entity to set the alignment anchor (default 08:00); the
  existing **Analysis Interval** entity now feeds this mechanism instead of
  writing directly to the coordinator's update interval. Both are now also
  configurable directly from the setup and options wizard, in a new
  **Synchronization** section.

## 1.2.0

### Requirements (breaking)
- **Home Assistant 2026.3.0 or newer** (`hacs.json`), i.e. the first release shipped with
  Python 3.14. The test suite passes on 2026.3.0 and 2026.9.3.

### Added
- **Raw ORP (mV)** diagnostic sensor, next to the existing raw pH: the probe value *before* any
  offset, to calibrate on a reference solution.

### Removed (breaking)
- Sensors **Estimated Free Chlorine** and **Active Chlorine (HOCl)**. Why:
  - **ORP is not a concentration.** For the same chlorine level it changes with pH, temperature,
    stabilizer (CYA), other oxidisers and probe ageing; one mV value cannot be turned into ppm.
  - **The conversion could show chlorine where there is none.** The formula was floored at 415 mV,
    so every lower ORP gave the same result: at pH 7.2 with no stabilizer, **100 mV** (no oxidiser)
    still displayed 0.1 ppm free chlorine and 0.07 mg/L HOCl.
  - **Stacked, unvalidated CYA corrections.** Free chlorine was multiplied by CYA/40 and HOCl was
    divided by a second CYA factor: with identical ORP/pH/temperature, HOCl went from 0.66 mg/L
    (no stabilizer) to 0.02 mg/L (40 mg/L), a x33 swing, with no measurement data to support it.
  - **Documentation claimed more than the code did** ("Machine Learning" model), giving a false
    sense of accuracy.
  - **Chlorine is a safety measure**: a wrong but precise-looking value is worse than none.
  - Use the ORP value with your own thresholds and a test kit for the actual chlorine level.
- Orphan entities are removed automatically on upgrade (config entry minor version 1.1 → 1.2,
  a downgrade stays possible). The CyA entity, the treatment selector (chlorine/bromine) and
  their options are **kept** but no longer influence any computed value.

### Changed (same behaviour as Blue Connect Local)
- **Bluetooth signal sensor (RSSI)** becomes *unavailable* as soon as the Flipr is out of range and is
  available again when it comes back. Before, it kept displaying its last value indefinitely.
- **"New analysis" button** now tries to connect even when no recent advertisement was received
  (before, it was refused with a warning). Scheduled analyses are still skipped while out of range.
  A forced analysis is now consumed by the cycle that receives it, whatever its outcome, so it can
  no longer stay armed and bypass the pause later.

### Fixed
- Invalid BLE frames retried forever: `retry_count` was reset before the frame was decoded, so the
  retry budget never ran out and the "unreachable after retries" state was never reached.
- CyA entered on the entity was reverted to the old options value whenever another setting
  (e.g. treatment type) changed.
- Coordinator `async_shutdown` did not call the parent implementation (scheduled refresh and
  debouncer were left running after unload).
- Calibration errors of the options flow had no translated text in any language.
- `nl.json` and `pt-br.json` contained a duplicated `"sections"` key, hiding the labels of the
  general / calibration sections in the options form.
- `validate_calibration` raised on a non-numeric ORP / offset / CyA value.
- Stored data restored at startup no longer re-injects the removed chlorine values.

### Hardened
- Degenerate pH calibration falls back to the factory calibration instead of silently returning 7.0.
- A computed pH outside 0-14 becomes *unknown* instead of being displayed.
- Langelier index and equilibrium pH reject NaN/inf inputs; so does the mV/pH calibration input conversion.

### Internal
- Code split into single-purpose modules: `coordinator.py` (BLE cycle, was 900 lines of `__init__.py`),
  `frame.py` (BLE frame decoding), `model.py` (model from BLE name), `validation.py` (form validation);
  calibration helpers moved to `chemistry.py`;
  duplicated derivation code merged; BLE timings are named constants.
- Test suite rewritten (the previous one could not even be imported): ~390 tests incl.
  property-based tests, fake Bluetooth, config/options flow, migration, translations consistency.
- CI: pytest + coverage workflow (Python 3.14); explicit ruff configuration in `pyproject.toml`;
  `requirements_test.txt`; test artefacts added to `.gitignore`.
- The coordinator receives its `config_entry` explicitly; `store_key` / `format_mac_safe` / `get_opt`
  are now public helpers of `coordinator.py`.
- Code style: Python 3.14 syntax `except A, B:` (what ruff formats for that target).

### Documentation
- `README.md` / `README.fr.md`: chlorine removal explained, raw ORP, minimum Home Assistant version,
  development section. `calibration_help.md`: raw ORP calibration, "Chlore / Redox Statut" label
  corrected to "Redox Statut". `info.md`: unfounded "Machine Learning" claim removed.
