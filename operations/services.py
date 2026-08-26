"""
Production Scheduling & Chunking Services (operations/services.py)
------------------------------------------------------------------
Implements 24/7 Continuous Backward Scheduling and Hourly Chunking for production line workers.

- Continuous 24/7 operation: Orders can be picked up at any hour of the day.
- Orders are decomposed into hourly production chunks based on FactorySettings.palettes_per_hour.
- Chunks are scheduled backwards from the order's pickup_time continuously across the 24-hour timeline.
  If scheduling goes past midnight backwards, it seamlessly schedules into the previous day.
- Tasks are sorted chronologically by scheduled production date and hour (earliest first),
  so the current / earliest task is at the top of the queue.
- Hourly availability matrix generates a full 24-hour slot list (00:00 to 23:59) with capacity
  strictly equal to FactorySettings.palettes_per_hour.
"""

import math
import datetime
from typing import List, Dict, Any, Optional
from django.utils import timezone
from operations.models import FactorySettings, Order, OrderItem


def get_factory_settings():
    """Fetches the active FactorySettings singleton."""
    return FactorySettings.get_settings()


def split_order_into_hourly_chunks(
    order: Optional[Order] = None,
    palettes_count: Optional[float] = None,
    pickup_time: Optional[datetime.time] = None,
    target_date: Optional[datetime.date] = None,
    settings: Optional[FactorySettings] = None,
    palettes_per_hour: Optional[float] = None,
    kg_per_palette: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Splits an order (or given palette amount) into hourly production chunks
    and schedules them BACKWARDS continuously from the pickup_time across a 24-hour timeline.
    If it goes past midnight backwards, it seamlessly schedules into the previous day.

    Example:
        15 palettes, capacity = 5 palettes/hour, pickup_time = 18:00
        -> 3 chunks of 5 palettes each:
           - Chunk 1: 15:00 - 16:00 (5 palettes)
           - Chunk 2: 16:00 - 17:00 (5 palettes)
           - Chunk 3: 17:00 - 18:00 (5 palettes)

        Example across midnight:
        15 palettes, capacity = 5 palettes/hour, pickup_time = 02:00 on 2026-08-25
        -> 3 chunks:
           - Chunk 1: 23:00 - 00:00 on 2026-08-24 (5 palettes)
           - Chunk 2: 00:00 - 01:00 on 2026-08-25 (5 palettes)
           - Chunk 3: 01:00 - 02:00 on 2026-08-25 (5 palettes)

    Returns:
        List of chunk dictionaries sorted chronologically (earliest start time first).
    """
    if settings is None:
        settings = get_factory_settings()

    # Safe float conversions
    try:
        pal_per_hr = float(palettes_per_hour or getattr(settings, 'palettes_per_hour', 2.0))
    except (ValueError, TypeError):
        pal_per_hr = 2.0
    if pal_per_hr <= 0 or math.isnan(pal_per_hr) or math.isinf(pal_per_hr):
        pal_per_hr = 2.0

    try:
        kg_per_pal = float(kg_per_palette or getattr(settings, 'kg_per_palette', 625.0))
    except (ValueError, TypeError):
        kg_per_pal = 625.0
    if kg_per_pal <= 0 or math.isnan(kg_per_pal) or math.isinf(kg_per_pal):
        kg_per_pal = 625.0

    if order is not None:
        if pickup_time is None:
            pickup_time = getattr(order, 'pickup_time', None) or datetime.time(18, 0)
        if palettes_count is None:
            pending_items = order.orderitem_set.filter(status='pending')
            total_kg = sum(item.quantity for item in pending_items)
            if total_kg == 0 and order.orderitem_set.exists():
                total_kg = sum(item.quantity for item in order.orderitem_set.all())
            palettes_count = (total_kg / kg_per_pal) if kg_per_pal > 0 else 0.0

    if pickup_time is None:
        pickup_time = datetime.time(18, 0)

    if palettes_count is None:
        return []

    try:
        total_palettes = float(palettes_count)
    except (ValueError, TypeError):
        return []

    if total_palettes <= 0 or math.isnan(total_palettes) or math.isinf(total_palettes):
        return []

    if target_date is None:
        if order and order.created_at:
            target_date = order.created_at.date()
        else:
            target_date = timezone.localtime().date()

    # Calculate chunk count with safety cap
    num_chunks = int(math.ceil(total_palettes / pal_per_hr))
    if num_chunks <= 0:
        return []
    num_chunks = min(num_chunks, 100)  # Max 100 chunks safeguard

    # Distribute palettes across finite chunks
    chunk_sizes = []
    remaining = total_palettes
    for _ in range(num_chunks):
        if remaining <= 0:
            break
        chunk_val = min(remaining, pal_per_hr)
        chunk_sizes.append(chunk_val)
        remaining -= chunk_val

    if not chunk_sizes:
        return []

    # Backward scheduling from pickup_time across 24h timeline
    pickup_dt = datetime.datetime.combine(target_date, pickup_time)
    k = len(chunk_sizes)
    chunks = []

    product_summary = "Kartoffeln"
    if order and order.orderitem_set.exists():
        items_list = [f"{item.quantity}kg {item.menu_item.name}" for item in order.orderitem_set.all()]
        product_summary = ", ".join(items_list)

    customer_name = "Kunde"
    if order and order.user:
        customer_name = order.user.get_full_name() or order.user.username

    for idx, size in enumerate(chunk_sizes):
        # idx=0 is earliest chunk, idx=k-1 is the chunk directly preceding pickup_time
        hours_before = k - idx
        start_dt = pickup_dt - datetime.timedelta(hours=hours_before)
        end_dt = pickup_dt - datetime.timedelta(hours=hours_before - 1)

        start_time = start_dt.time()
        end_time = end_dt.time()
        chunk_date = start_dt.date()
        quantity_kg = size * kg_per_pal

        chunks.append({
            'chunk_index': idx + 1,
            'total_chunks': k,
            'palettes': round(size, 2),
            'quantity_kg': round(quantity_kg, 1),
            'start_time': start_time,
            'end_time': end_time,
            'start_time_str': start_time.strftime('%H:%M'),
            'end_time_str': end_time.strftime('%H:%M'),
            'time_slot': f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}",
            'pickup_time': pickup_time,
            'pickup_time_str': pickup_time.strftime('%H:%M'),
            'target_date': chunk_date,
            'pickup_date': target_date,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'order': order,
            'order_id': order.id if order else None,
            'customer_name': customer_name,
            'product_summary': product_summary,
            'is_current': False,
        })

    # Sort chronologically by scheduled production date and hour (earliest first)
    chunks = sorted(chunks, key=lambda c: (c['target_date'], c['start_time']))
    return chunks


def get_production_tasks(
    orders=None,
    target_date: Optional[datetime.date] = None,
    target_dates: Optional[List[datetime.date]] = None,
    settings: Optional[FactorySettings] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves and schedules all pending production tasks across active orders,
    sorted chronologically with the earliest/current task at index 0.

    If target_dates (list of dates) or target_date (single date) is provided,
    only tasks scheduled for those target dates are returned.
    """
    if settings is None:
        settings = get_factory_settings()

    allowed_dates = None
    if target_dates is not None:
        allowed_dates = set(target_dates)
    elif target_date is not None:
        allowed_dates = {target_date}

    if orders is None:
        orders = Order.objects.filter(
            status='pending'
        ).prefetch_related('orderitem_set', 'orderitem_set__menu_item', 'user').order_by('pickup_time', 'created_at')

    all_tasks = []
    for order in orders:
        order_chunks = split_order_into_hourly_chunks(
            order=order,
            target_date=target_date,
            settings=settings
        )
        if allowed_dates is not None:
            order_chunks = [c for c in order_chunks if c['target_date'] in allowed_dates]
        all_tasks.extend(order_chunks)

    # Sort all tasks strictly chronologically across all orders
    all_tasks = sorted(all_tasks, key=lambda t: (t['target_date'], t['start_time'], t['order_id'] or 0, t['chunk_index']))

    # Mark the first task as current
    for idx, task in enumerate(all_tasks):
        task['is_current'] = (idx == 0)

    return all_tasks


def get_hourly_availability(
    target_date: Optional[datetime.date] = None,
    settings: Optional[FactorySettings] = None
) -> List[Dict[str, Any]]:
    """
    Calculates 24/7 hourly capacity availability for a given date across the full 24-hour timeline (00:00 to 23:59).

    Completely ignores shift start/end times.
    Generates 24 slots (00:00 to 23:59) where total capacity per hour is FactorySettings.palettes_per_hour.

    For each hour slot from 00:00 to 23:00, calculates:
        - total: FactorySettings.palettes_per_hour
        - used: palettes already scheduled for that hour across active orders
        - remaining: max(0, total - used)

    Returns a list of 24 dictionaries:
        [{'time': '00:00 - 01:00', 'total': 5.0, 'used': 0.0, 'remaining': 5.0, ...}, ...]
    """
    if settings is None:
        settings = get_factory_settings()

    if target_date is None:
        target_date = timezone.localtime().date()

    pal_per_hr = float(getattr(settings, 'palettes_per_hour', 2.0))
    if pal_per_hr <= 0:
        pal_per_hr = 2.0
    kg_per_pal = float(getattr(settings, 'kg_per_palette', 625.0))
    if kg_per_pal <= 0:
        kg_per_pal = 625.0

    # Fetch all tasks on target_date
    tasks = get_production_tasks(target_date=target_date, settings=settings)

    # Aggregate used palettes by start hour
    used_by_hour = {}
    for task in tasks:
        if task.get('target_date') == target_date:
            h = task['start_time'].hour
            used_by_hour[h] = used_by_hour.get(h, 0.0) + float(task['palettes'])

    hourly_slots = []
    for h in range(0, 24):
        start_t = datetime.time(h, 0)
        end_t = datetime.time((h + 1) % 24, 0)
        start_str = f"{h:02d}:00"
        end_str = f"{(h + 1) % 24:02d}:00"
        time_label = f"{start_str} - {end_str}"

        used = round(used_by_hour.get(h, 0.0), 2)
        remaining = max(0.0, round(pal_per_hr - used, 2))

        total_kg = round(pal_per_hr * kg_per_pal, 1)
        used_kg = round(used * kg_per_pal, 1)
        remaining_kg = round(remaining * kg_per_pal, 1)

        if used == 0:
            status = 'free'
            badge_class = 'success'
            status_label = f"{remaining:.1f} Pal. frei" if remaining != int(remaining) else f"{int(remaining)} Pal. frei"
        elif remaining <= 0:
            status = 'full'
            badge_class = 'danger'
            status_label = "0 Pal. (Voll)"
        else:
            status = 'partial'
            badge_class = 'warning'
            status_label = f"{remaining:.1f} Pal. frei" if remaining != int(remaining) else f"{int(remaining)} Pal. frei"

        hourly_slots.append({
            'time': time_label,
            'start_time': start_t,
            'end_time': end_t,
            'start_str': start_str,
            'end_str': end_str,
            'total': pal_per_hr,
            'used': used,
            'remaining': remaining,
            'total_kg': total_kg,
            'used_kg': used_kg,
            'remaining_kg': remaining_kg,
            'status': status,
            'badge_class': badge_class,
            'status_label': status_label,
        })

    return hourly_slots


