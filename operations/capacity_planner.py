"""
Capacity Planner Module (operations/capacity_planner.py)
--------------------------------------------------------
Dynamic production capacity planning and scheduling logic for Kartoffelfirma.

The baseline factory capacity is configured in palettes per hour and weight per palette:
- hourly_production_target_kg = palettes_per_hour * kg_per_palette
- daily_production_target_kg = hourly_production_target_kg * 24
All parameters are loaded dynamically from the singleton FactorySettings model.
"""

import datetime
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db.models import Sum, Q


def get_factory_settings():
    """
    Fetches the active FactorySettings singleton instance dynamically from the database.
    """
    from operations.models import FactorySettings
    return FactorySettings.get_settings()


def get_palettes_per_hour(settings=None) -> float:
    """
    Returns the dynamic rate of palettes produced per hour (e.g. 2.0).
    """
    if settings is None:
        settings = get_factory_settings()
    return float(settings.palettes_per_hour)


def get_kg_per_palette(settings=None) -> float:
    """
    Returns the dynamic weight of a single palette in kg (e.g. 625.0 kg).
    """
    if settings is None:
        settings = get_factory_settings()
    return float(settings.kg_per_palette)


def get_hourly_production_target_kg(settings=None) -> float:
    """
    Returns the dynamic hourly production target in kg/h (palettes_per_hour * kg_per_palette).
    """
    if settings is None:
        settings = get_factory_settings()
    return float(settings.hourly_production_target_kg)


def get_daily_production_target_kg(settings=None) -> float:
    """
    Returns the calculated 24h daily production capacity in kg (hourly_production_target_kg * 24).
    """
    if settings is None:
        settings = get_factory_settings()
    return float(settings.daily_production_target_kg)


def get_cutoff_time(settings=None) -> datetime.time:
    """
    Returns the dynamic next-day cutoff time (e.g. 22:00:00).
    """
    if settings is None:
        settings = get_factory_settings()
    return settings.next_day_cutoff_time


def determine_target_production_date(order_time: Optional[datetime.datetime] = None, settings=None) -> datetime.date:
    """
    Determines the target production date based on the dynamic cutoff time.
    If the order time is on or after next_day_cutoff_time, the order is automatically
    scheduled for the following day (order_date + 1 day). Otherwise, it is scheduled
    for the current order date.
    """
    if settings is None:
        settings = get_factory_settings()

    if order_time is None:
        order_time = timezone.localtime()
    elif timezone.is_aware(order_time):
        order_time = timezone.localtime(order_time)

    cutoff_time = settings.next_day_cutoff_time
    order_time_of_day = order_time.time()
    order_date = order_time.date()

    if order_time_of_day >= cutoff_time:
        return order_date + datetime.timedelta(days=1)
    return order_date


def get_scheduled_production_kg(target_date: datetime.date) -> float:
    """
    Calculates total kg already scheduled/ordered for the given production date.
    Excludes cancelled order items.
    """
    from operations.models import OrderItem

    scheduled = OrderItem.objects.filter(
        Q(order__delivery_date=target_date) |
        (Q(order__delivery_date__isnull=True) & Q(order__created_at__date=target_date))
    ).exclude(
        status='cancelled'
    ).aggregate(total_kg=Sum('quantity'))['total_kg']

    return float(scheduled or 0.0)



def get_remaining_daily_capacity_kg(target_date: datetime.date, settings=None) -> float:
    """
    Calculates the remaining production capacity in kg for the given date.
    Remaining = max(0, daily_production_target_kg - scheduled_production_kg).
    """
    if settings is None:
        settings = get_factory_settings()

    target_kg = get_daily_production_target_kg(settings)
    scheduled_kg = get_scheduled_production_kg(target_date)
    return max(0.0, target_kg - scheduled_kg)


def check_order_capacity(
    order_kg: float,
    target_date: Optional[datetime.date] = None,
    order_time: Optional[datetime.datetime] = None,
    settings=None,
    max_search_days: int = 14
) -> Dict[str, Any]:
    """
    Validates if an incoming order in kg can be accommodated within the
    daily production target (palettes_per_hour * kg_per_palette * 24) for the requested or computed target date.

    - Dynamically evaluates hourly_production_target_kg * 24 from FactorySettings.
    - Automatically shifts date if order_time is after next_day_cutoff_time (when target_date not explicitly set).
    - If capacity is exceeded, automatically searches forward up to `max_search_days` to find
      the next available date with sufficient capacity.

    Returns a detailed capacity evaluation dictionary:
        - is_feasible: bool
        - target_date: datetime.date
        - requested_kg: float
        - palettes_per_hour: float
        - kg_per_palette: float
        - hourly_production_target_kg: float
        - daily_production_target_kg: float (24h total)
        - already_allocated_kg: float
        - remaining_capacity_kg: float
        - exceeded_by_kg: float (0.0 if feasible)
        - is_after_cutoff: bool
        - cutoff_time: datetime.time
        - suggested_next_available_date: Optional[datetime.date]
        - utilization_percent: float
        - message: str
    """
    if settings is None:
        settings = get_factory_settings()

    if order_time is None:
        order_time = timezone.localtime()
    elif timezone.is_aware(order_time):
        order_time = timezone.localtime(order_time)

    cutoff_time = settings.next_day_cutoff_time
    is_after_cutoff = (order_time.time() >= cutoff_time)

    if target_date is None:
        target_date = determine_target_production_date(order_time, settings)

    order_kg = max(0.0, float(order_kg))
    palettes_per_hr = get_palettes_per_hour(settings)
    kg_per_pal = get_kg_per_palette(settings)
    hourly_target_kg = get_hourly_production_target_kg(settings)
    daily_target_kg = get_daily_production_target_kg(settings)
    already_allocated = get_scheduled_production_kg(target_date)
    remaining_capacity = max(0.0, daily_target_kg - already_allocated)

    is_feasible = (order_kg <= remaining_capacity)
    exceeded_by = max(0.0, order_kg - remaining_capacity)

    projected_total = already_allocated + order_kg
    utilization_percent = round((projected_total / daily_target_kg * 100.0), 1) if daily_target_kg > 0 else 100.0

    suggested_date = None
    if not is_feasible:
        # Search next available days
        curr_search_date = target_date + datetime.timedelta(days=1)
        for _ in range(max_search_days):
            day_remaining = get_remaining_daily_capacity_kg(curr_search_date, settings)
            if order_kg <= day_remaining:
                suggested_date = curr_search_date
                break
            curr_search_date += datetime.timedelta(days=1)

    if is_feasible:
        if is_after_cutoff:
            msg = (
                f"Kapazität verfügbar für den {target_date.strftime('%d.%m.%Y')} "
                f"(nach Cut-off-Zeit {cutoff_time.strftime('%H:%M')} Uhr auf Folgetag verschoben). "
                f"Verbleibend nach Auftrag: {remaining_capacity - order_kg:.1f} kg."
            )
        else:
            msg = (
                f"Kapazität verfügbar für den {target_date.strftime('%d.%m.%Y')}. "
                f"Verbleibend nach Auftrag: {remaining_capacity - order_kg:.1f} kg."
            )
    else:
        msg = (
            f"Kapazität für {target_date.strftime('%d.%m.%Y')} überschritten um {exceeded_by:.1f} kg. "
            f"Tageskapazität (24h): {daily_target_kg:.0f} kg ({hourly_target_kg:.0f} kg/h), bereits belegt: {already_allocated:.1f} kg."
        )
        if suggested_date:
            msg += f" Nächster freier Liefertermin: {suggested_date.strftime('%d.%m.%Y')}."

    return {
        'is_feasible': is_feasible,
        'target_date': target_date,
        'requested_kg': order_kg,
        'palettes_per_hour': palettes_per_hr,
        'kg_per_palette': kg_per_pal,
        'hourly_production_target_kg': hourly_target_kg,
        'daily_production_target_kg': daily_target_kg,
        'already_allocated_kg': already_allocated,
        'remaining_capacity_kg': remaining_capacity,
        'exceeded_by_kg': exceeded_by,
        'is_after_cutoff': is_after_cutoff,
        'cutoff_time': cutoff_time,
        'suggested_next_available_date': suggested_date,
        'utilization_percent': utilization_percent,
        'message': msg,
    }


def is_within_buro_hours(check_time: Optional[datetime.time] = None, settings=None) -> bool:
    """
    Checks if the given time (or current time) falls within configured Büro working hours.
    """
    if settings is None:
        settings = get_factory_settings()
    if check_time is None:
        check_time = timezone.localtime().time()

    start = settings.buro_working_start
    end = settings.buro_working_end
    if start <= end:
        return start <= check_time <= end
    # Overnight shift support
    return check_time >= start or check_time <= end


def is_within_production_hours(check_time: Optional[datetime.time] = None, settings=None) -> bool:
    """
    Checks if the given time (or current time) falls within configured Produktion working hours.
    """
    if settings is None:
        settings = get_factory_settings()
    if check_time is None:
        check_time = timezone.localtime().time()

    start = settings.production_working_start
    end = settings.production_working_end
    if start <= end:
        return start <= check_time <= end
    # Overnight shift support
    return check_time >= start or check_time <= end


def get_capacity_summary(start_date: Optional[datetime.date] = None, days: int = 7, settings=None) -> list:
    """
    Generates a multi-day capacity outlook summary table starting from start_date.
    """
    if settings is None:
        settings = get_factory_settings()
    if start_date is None:
        start_date = timezone.localtime().date()

    palettes_per_hr = float(settings.palettes_per_hour)
    kg_per_pal = float(settings.kg_per_palette)
    hourly_target = float(settings.hourly_production_target_kg)
    daily_target = float(settings.daily_production_target_kg)
    summary = []

    for i in range(days):
        day_date = start_date + datetime.timedelta(days=i)
        scheduled = get_scheduled_production_kg(day_date)
        remaining = max(0.0, daily_target - scheduled)
        utilization = round((scheduled / daily_target * 100.0), 1) if daily_target > 0 else 0.0

        summary.append({
            'date': day_date,
            'day_name': day_date.strftime('%A'),
            'palettes_per_hour': palettes_per_hr,
            'kg_per_palette': kg_per_pal,
            'hourly_target_kg': hourly_target,
            'daily_target_kg': daily_target,
            'scheduled_kg': scheduled,
            'remaining_kg': remaining,
            'utilization_percent': utilization,
            'is_fully_booked': remaining <= 0.0,
        })

    return summary
