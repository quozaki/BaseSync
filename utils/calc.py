from math import isfinite
from .loading import load_units, load_rates

_units = None
_rates = None
EPSILON = 1e-9


def _ensure_data_loaded():
    global _units, _rates
    if _units is None:
        _units = load_units()
    if _rates is None:
        _rates = load_rates()


def get_units():
    _ensure_data_loaded()
    return _units


def get_rates():
    _ensure_data_loaded()
    return _rates


def reload_data():
    """Reload units and rate data from disk."""
    global _units, _rates
    _units = load_units()
    _rates = load_rates()
    return _units, _rates


def _normalize_unit(unit):
    if unit is None:
        return ""
    return str(unit).lower().strip()


def _normalize_bases(bases):
    if isinstance(bases, bool):
        return None
    if isinstance(bases, int):
        return bases
    if isinstance(bases, float) and bases.is_integer():
        return int(bases)
    if isinstance(bases, str) and bases.strip().isdigit():
        return int(bases.strip())
    return None


def _is_positive_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value > 0
    )


def _is_non_negative_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value >= 0
    )


def _validate_unit_record(record):
    if not isinstance(record, dict):
        return "Invalid unit definition"
    if "steel" not in record or "aluminium" not in record or "time" not in record:
        return "Invalid unit schema"
    if not _is_positive_number(record["steel"]):
        return "Invalid unit steel cost"
    if not _is_positive_number(record["aluminium"]):
        return "Invalid unit aluminium cost"
    if not _is_positive_number(record["time"]):
        return "Invalid unit time"
    return None


def _validate_storages(steel_storage, alum_storage):
    if steel_storage is None and alum_storage is None:
        return None
    if steel_storage is None or alum_storage is None:
        return "Both steel and aluminium storage values must be provided together"
    if not _is_non_negative_number(steel_storage):
        return "Invalid steel storage"
    if not _is_non_negative_number(alum_storage):
        return "Invalid aluminium storage"
    return None


def _clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def _run_simulation(time, steel_cost, aluminium_cost, pps, steel_storage=None, alum_storage=None):
    storage_enabled = steel_storage is not None and alum_storage is not None

    if storage_enabled:
        current_steel = steel_storage - steel_cost
        current_alum = alum_storage - aluminium_cost
    else:
        current_steel = 0.0
        current_alum = 0.0

    steel_states = [current_steel]
    alum_states = [current_alum]
    current_time = 0.0
    produced = 1
    start_times = [0.0]

    while current_time + EPSILON < time:
        needed_steel = max(0.0, steel_cost - current_steel)
        needed_alum = max(0.0, aluminium_cost - current_alum)

        if needed_steel <= EPSILON and needed_alum <= EPSILON:
            current_steel -= steel_cost
            current_alum -= aluminium_cost
            produced += 1
            start_times.append(current_time)
            steel_states.append(current_steel)
            alum_states.append(current_alum)
            continue

        time_steel = needed_steel / pps
        time_alum = needed_alum / pps
        wait_time = max(time_steel, time_alum)

        if wait_time <= EPSILON or current_time + wait_time > time:
            break

        current_time += wait_time

        if storage_enabled:
            current_steel = min(steel_storage, current_steel + pps * wait_time)
            current_alum = min(alum_storage, current_alum + pps * wait_time)

            if current_steel + EPSILON < steel_cost or current_alum + EPSILON < aluminium_cost:
                continue
        else:
            current_steel += pps * wait_time
            current_alum += pps * wait_time

        current_steel -= steel_cost
        current_alum -= aluminium_cost
        produced += 1
        start_times.append(current_time)
        steel_states.append(current_steel)
        alum_states.append(current_alum)

    removed_units = 0
    while produced > 1 and start_times:
        last_start = start_times[-1]
        gap_time = time - last_start
        regen_steel = steel_states[-1] + (pps * gap_time)
        regen_alum = alum_states[-1] + (pps * gap_time)

        if regen_steel >= steel_cost and regen_alum >= aluminium_cost:
            break

        start_times.pop()
        steel_states.pop()
        alum_states.pop()
        produced -= 1
        removed_units += 1

    start_times_minutes = [round(start / 60.0, 2) for start in start_times]
    formatted_schedule = [
        "Unit 1: now"
        if idx == 1
        else f"Unit {idx}: after {minutes} min"
        for idx, minutes in enumerate(start_times_minutes, start=1)
    ]

    warning = ""
    if removed_units > 0:
        if storage_enabled:
            warning = (
                "⚠️ "
                f"{removed_units} unit(s) removed because they prevent the next {time/60.0:.1f}-minute "
                "session from starting immediately"
            )
        else:
            warning = (
                "⚠️ "
                f"{removed_units} unit(s) removed to ensure next session can start immediately"
            )

    return {
        "produced": produced,
        "start_times": start_times_minutes,
        "schedule": formatted_schedule,
        "removed_units": removed_units,
        "warning": warning,
    }


def calc_z(bases):
    return 14.4 * get_rates()[bases]


def calc_w(bases):
    z = calc_z(bases)
    return z * bases


def calc_max_bases_supported(unit, bases):
    units = get_units()
    rates = get_rates()

    unit_key = _normalize_unit(unit)
    if not unit_key:
        raise ValueError("Invalid unit")
    if unit_key not in units:
        raise ValueError("Invalid unit")

    unit_record = units[unit_key]
    validation_error = _validate_unit_record(unit_record)
    if validation_error:
        raise ValueError(validation_error)

    bases_int = _normalize_bases(bases)
    if bases_int is None or bases_int <= 0:
        raise ValueError("Invalid number of bases")
    if bases_int not in rates:
        raise ValueError("Invalid number of bases")

    rate = rates[bases_int]
    if not _is_positive_number(rate):
        raise ValueError("Invalid base rate")

    time = unit_record["time"]
    steel = unit_record["steel"]
    aluminium = unit_record["aluminium"]

    w = calc_w(bases_int)
    p = (w * time) / 3600.0
    if not _is_positive_number(p):
        raise ValueError("Invalid production rate")

    steel_capacity = p * 1000.0 / steel
    aluminium_capacity = p * 1000.0 / aluminium
    supported = min(steel_capacity, aluminium_capacity)

    if supported < 0 or not isfinite(supported):
        raise ValueError("Invalid calculation")

    return int(supported)


def simulate_sync(unit, bases, steel_storage=None, alum_storage=None):
    units = get_units()
    rates = get_rates()

    unit_key = _normalize_unit(unit)
    if not unit_key:
        return "Invalid unit"
    if unit_key not in units:
        return "Invalid unit"

    unit_record = units[unit_key]
    validation_error = _validate_unit_record(unit_record)
    if validation_error:
        return validation_error

    bases_int = _normalize_bases(bases)
    if bases_int is None or bases_int <= 0:
        return "Invalid number of bases"
    if bases_int not in rates:
        return "Invalid number of bases"

    storage_error = _validate_storages(steel_storage, alum_storage)
    if storage_error:
        return storage_error

    time = unit_record["time"]
    steel_cost = unit_record["steel"]
    aluminium_cost = unit_record["aluminium"]
    w = calc_w(bases_int)
    pps = w * 1000.0 / 3600.0

    if not _is_positive_number(pps):
        return "Invalid production rate"

    return _run_simulation(
        time,
        steel_cost,
        aluminium_cost,
        pps,
        steel_storage=steel_storage,
        alum_storage=alum_storage,
    )

