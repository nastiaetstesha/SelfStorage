from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login  # Этого импорта не хватало!
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Max, Min
from django.urls import reverse
from decimal import Decimal

from .models import Warehouse, Box, StorageRule, Rental, PriceCalculationRequest, UserProfile

DEFAULT_TEMPERATURE_C = 18


def index(request):
    warehouse = Warehouse.objects.filter(is_active=True).order_by("city", "title").first()

    # если нажали "Рассчитать стоимость" — сохраняем заявку
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        source = (request.POST.get("source") or "hero").strip()

        if email:
            PriceCalculationRequest.objects.create(
                email=email,
                source=source,
                warehouse=warehouse,
                user=request.user if request.user.is_authenticated else None,
            )
        return redirect(reverse("storage:index"))

    if not warehouse:
        return render(request, "storage/index.html", {"warehouse": None})

    total_boxes = warehouse.total_boxes_count()
    free_boxes = warehouse.available_boxes_count()

    busy_ids = Rental.objects.filter(
        status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE]
    ).values_list("box_id", flat=True)

    free_boxes_qs = Box.objects.filter(
        warehouse=warehouse,
        is_active=True,
    ).exclude(id__in=busy_ids)

    min_month_price = free_boxes_qs.aggregate(m=Min("length_m"))

    min_price = None
    prices = list(free_boxes_qs.values_list("length_m", "width_m", "height_m"))
    if prices:
        from .models import PRICE_PER_M3_PER_MONTH
        min_price = min(
            (Decimal(l) * Decimal(w) * Decimal(h) * PRICE_PER_M3_PER_MONTH).quantize(Decimal("0.01"))
            for l, w, h in prices
        )

    max_ceiling = Box.objects.filter(warehouse=warehouse, is_active=True).aggregate(
        m=Max("height_m")
    )["m"]

    photo_url = warehouse.photo.url if warehouse.photo else None

    context = {
        "warehouse": warehouse,
        "total_boxes": total_boxes,
        "free_boxes": free_boxes,
        "min_month_price": min_price,
        "temperature_c": DEFAULT_TEMPERATURE_C,
        "ceiling_height_m": max_ceiling,
        "photo_url": photo_url,
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


def login_redirect(request):
    """
    Страница входа.
    Получает параметр next (куда вернуться после входа)
    и показывает главную с открытым модальным окном
    """
    # Получаем URL, на который нужно вернуться после входа
    next_url = request.GET.get('next', '')

    # Рендерим главную страницу и передаем флаг для открытия модалки
    return render(request, "storage/index.html", {
        "open_login_modal": True,  # Флаг для открытия модального окна
        "next_url": next_url  # Адрес для возврата
    })


def register(request):
    """Регистрация и вход по email"""
    if request.method == 'POST':
        email = request.POST.get('email')
        next_url = request.POST.get('next', '')  # 👈 Получаем next из формы

        if email:
            user, created = User.objects.get_or_create(
                username=email,
                defaults={'email': email}
            )

            # Создаем профиль для нового пользователя
            if created:
                UserProfile.objects.create(user=user)

            login(request, user)

            # Если есть next_url и он не пустой, перенаправляем туда
            if next_url and next_url.strip():
                return redirect(next_url)

            # Иначе в личный кабинет
            return redirect('storage:my_rent')

    return redirect('storage:index')


@login_required
def my_rent(request):
    # Получаем или создаем профиль пользователя
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Обработка POST запроса (сохранение данных)
    if request.method == 'POST':
        # Обновляем телефон
        phone = request.POST.get('phone')
        if phone is not None:  # Разрешаем пустой телефон
            profile.phone = phone

        # Обновляем фото
        if request.FILES.get('avatar'):
            # Удаляем старое фото, если оно было
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = request.FILES['avatar']

        profile.save()
        return redirect('storage:my_rent')

    # Получаем аренды пользователя
    rentals = Rental.objects.filter(user=request.user).order_by("-created_at")
    active_rentals = rentals.filter(status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE])

    return render(
        request,
        "storage/my-rent.html",
        {
            'user': request.user,
            "profile": profile,
            "rentals": rentals,
            "active_rentals": active_rentals,
        },
    )