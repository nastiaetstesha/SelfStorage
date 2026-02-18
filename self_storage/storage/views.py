from django.shortcuts import render

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Max, Min
from django.shortcuts import render, get_object_or_404

from .models import Warehouse, Box, StorageRule, Rental


DEFAULT_TEMPERATURE_C = 18


def index(request):
    warehouse = Warehouse.objects.filter(is_active=True).order_by("city", "title").first()

    if not warehouse:
        return render(request, "storage/index.html", {"warehouse": None})

    total_boxes = warehouse.total_boxes_count()
    free_boxes = warehouse.available_boxes_count()

    # Свободные боксы: это те, у которых нет ACTIVE/OVERDUE аренды
    busy_ids = Rental.objects.filter(
        status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE]
    ).values_list("box_id", flat=True)

    free_boxes_qs = Box.objects.filter(
        warehouse=warehouse,
        is_active=True,
    ).exclude(id__in=busy_ids)

    min_month_price = free_boxes_qs.aggregate(m=Min("length_m"))  # заглушка чтобы не ругался линтер
    # На самом деле минимальную цену считаем так:
    min_price = None
    prices = list(free_boxes_qs.values_list("length_m", "width_m", "height_m"))
    if prices:
        # Box.price_per_month - property, поэтому Min() по нему не сделать напрямую без аннотации.
        
        from .models import PRICE_PER_M3_PER_MONTH
        min_price = min(
            (Decimal(l) * Decimal(w) * Decimal(h) * PRICE_PER_M3_PER_MONTH).quantize(Decimal("0.01"))
            for l, w, h in prices
        )

    max_ceiling = Box.objects.filter(warehouse=warehouse, is_active=True).aggregate(
        m=Max("height_m")
    )["m"]

    context = {
        "warehouse": warehouse,
        "total_boxes": total_boxes,
        "free_boxes": free_boxes,
        "min_month_price": min_price,
        "temperature_c": DEFAULT_TEMPERATURE_C,
        "ceiling_height_m": max_ceiling,
    }
    return render(request, "storage/index.html", context)


def faq(request):
    allowed = StorageRule.objects.filter(
        is_active=True, rule_type=StorageRule.RuleType.ALLOWED
    ).order_by("sort_order", "title")
    forbidden = StorageRule.objects.filter(
        is_active=True, rule_type=StorageRule.RuleType.FORBIDDEN
    ).order_by("sort_order", "title")

    return render(request, "storage/faq.html", {"allowed": allowed, "forbidden": forbidden})


def boxes(request):
    # показываем боксы выбранного склада (или первого активного)
    warehouse_id = request.GET.get("warehouse")
    if warehouse_id:
        warehouse = get_object_or_404(Warehouse, pk=warehouse_id, is_active=True)
    else:
        warehouse = Warehouse.objects.filter(is_active=True).order_by("city", "title").first()

    warehouses = Warehouse.objects.filter(is_active=True).order_by("city", "title")

    if not warehouse:
        return render(request, "storage/boxes.html", {"warehouse": None, "warehouses": warehouses, "boxes": []})

    busy_ids = Rental.objects.filter(
        status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE]
    ).values_list("box_id", flat=True)

    boxes_qs = Box.objects.filter(warehouse=warehouse, is_active=True).order_by("code")

    boxes_data = []
    for b in boxes_qs:
        is_free = b.id not in set(busy_ids)
        boxes_data.append(
            {
                "box": b,
                "is_free": is_free,
                "price_per_month": b.price_per_month,
                "volume_m3": b.volume_m3,
            }
        )

    return render(
        request,
        "storage/boxes.html",
        {
            "warehouse": warehouse,
            "warehouses": warehouses,
            "boxes": boxes_data,
        },
    )


@login_required
def my_rent(request):
    profile = getattr(request.user, "profile", None)
    rentals = Rental.objects.filter(user=request.user).order_by("-created_at")
    active = rentals.filter(status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE])

    return render(
        request,
        "storage/my-rent.html",
        {
            "profile": profile,
            "rentals": rentals,
            "active_rentals": active,
        },
    )
