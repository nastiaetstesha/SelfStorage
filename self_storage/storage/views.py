import random
import qrcode
from io import BytesIO
import base64
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Max, Min, F
from django.urls import reverse
from decimal import Decimal
from .models import (
    ShortLink,
    Warehouse,
    Box,
    StorageRule,
    Rental,
    PriceCalculationRequest,
    UserProfile,
    PromoCode,
)

DEFAULT_TEMPERATURE_C = 18


def generate_qr_code(data):
    """Генерирует QR-код и возвращает его как base64 строку"""
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=5,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#579586", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    image_png = buffer.getvalue()
    buffer.close()

    return base64.b64encode(image_png).decode()


def index(request):
    warehouse = (
        Warehouse.objects.filter(is_active=True).order_by("city", "title").first()
    )

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
            (Decimal(l) * Decimal(w) * Decimal(h) * PRICE_PER_M3_PER_MONTH).quantize(
                Decimal("0.01")
            )
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

    return render(
        request, "storage/faq.html", {"allowed": allowed, "forbidden": forbidden}
    )


def boxes(request):
    warehouse_id = request.GET.get("warehouse")
    if warehouse_id:
        warehouse = get_object_or_404(Warehouse, pk=warehouse_id, is_active=True)
    else:
        warehouse = (
            Warehouse.objects.filter(is_active=True).order_by("city", "title").first()
        )

    warehouses = Warehouse.objects.filter(is_active=True).order_by("city", "title")

    # Правила хранения (разрешённые и запрещённые вещи)
    allowed_rules = StorageRule.objects.filter(
        is_active=True, rule_type=StorageRule.RuleType.ALLOWED
    ).order_by("sort_order", "title")

    forbidden_rules = StorageRule.objects.filter(
        is_active=True, rule_type=StorageRule.RuleType.FORBIDDEN
    ).order_by("sort_order", "title")

    if request.method == "POST" and request.POST.get("action") == "pickup":
        pass

    busy_ids = set(
        Rental.objects.filter(
            status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE]
        ).values_list("box_id", flat=True)
    )

    # Список доступных изображений для складов (без повторений)
    warehouse_images = ["image11", "image15", "image16", "image151", "image9"]
    shuffled_images = warehouse_images.copy()
    random.shuffle(shuffled_images)

    warehouses_list = []
    for i, wh in enumerate(warehouses):
        wh_boxes_qs = Box.objects.filter(warehouse=wh, is_active=True).order_by("code")
        wh_boxes = []
        for b in wh_boxes_qs:
            is_free = b.id not in busy_ids
            wh_boxes.append({
                "box": b,
                "is_free": is_free,
                "price_per_month": b.price_per_month,
                "volume_m3": b.volume_m3,
            })

        # Вычисляем минимальную цену для этого склада
        min_price = None
        prices = list(wh_boxes_qs.values_list("length_m", "width_m", "height_m"))
        if prices:
            from .models import PRICE_PER_M3_PER_MONTH
            min_price = min(
                (Decimal(l) * Decimal(w) * Decimal(h) * PRICE_PER_M3_PER_MONTH).quantize(Decimal("0.01"))
                for l, w, h in prices
            )

        warehouses_list.append({
            "warehouse": wh,
            "boxes": wh_boxes,
            "min_price": min_price,
            "image_name": shuffled_images[i % len(shuffled_images)],
        })

    # Первый склад по умолчанию
    default_warehouse = warehouses[0] if warehouses else None
    default_boxes = warehouses_list[0]["boxes"] if warehouses_list else []

    price_estimates = [
        {"volume": "до 3 м³", "price": "от 1000 ₽"},
        {"volume": "3-10 м³", "price": "от 2500 ₽"},
        {"volume": "10+ м³", "price": "от 5000 ₽"},
    ]

    if not default_warehouse:
        return render(
            request,
            "storage/boxes.html",
            {
                "warehouse": None,
                "warehouses": warehouses,
                "warehouses_list": [],
                "boxes": [],
                "allowed_rules": allowed_rules,
                "forbidden_rules": forbidden_rules,
            },
        )

    return render(
        request,
        "storage/boxes.html",
        {
            "warehouse": default_warehouse,
            "warehouses": warehouses,
            "warehouses_list": warehouses_list,
            "boxes": default_boxes,
            "busy_ids": list(busy_ids),
            "allowed_rules": allowed_rules,
            "forbidden_rules": forbidden_rules,
            "price_estimates": price_estimates,
        },
    )


def login_redirect(request):
    """
    Страница входа.
    Получает параметр next (куда вернуться после входа)
    и показывает главную с открытым модальным окном
    """
    # Получаем URL, на который нужно вернуться после входа
    next_url = request.GET.get("next", "")

    # Рендерим главную страницу и передаем флаг для открытия модалки
    return render(
        request,
        "storage/index.html",
        {
            "open_login_modal": True,  # Флаг для открытия модального окна
            "next_url": next_url,  # Адрес для возврата
        },
    )


def register(request):
    """Регистрация и вход по email"""
    if request.method == "POST":
        email = request.POST.get("email")
        next_url = request.POST.get("next", "")  # Получаем next из формы

        if email:
            user, created = User.objects.get_or_create(
                username=email, defaults={"email": email}
            )

            # Создаем профиль для нового пользователя
            if created:
                UserProfile.objects.create(user=user)

            login(request, user)

            # Если есть next_url и он не пустой, перенаправляем туда
            if next_url and next_url.strip():
                return redirect(next_url)

            # Иначе в личный кабинет
            return redirect("storage:my_rent")

    return redirect("storage:index")


@login_required
def my_rent(request):
    user = request.user
    profile = UserProfile.objects.get(user=user)
    rentals = Rental.objects.filter(user=user)

    # Разделяем активные и завершенные аренды
    active_rentals = rentals.filter(status='active')
    other_rentals = rentals.exclude(status='active')

    # Добавляем QR-коды для каждой активной аренды
    for rental in active_rentals:
        # Формируем данные для QR-кода
        qr_data = {
            'box_code': rental.box.code,
            'warehouse': rental.box.warehouse.title,
            'address': rental.box.warehouse.address,
            'start_date': rental.start_date.strftime('%d.%m.%Y'),
            'end_date': rental.end_date.strftime('%d.%m.%Y'),
            'access_key': f"ACCESS_{rental.id}_{rental.box.code}"
        }

        # Генерируем QR-код и добавляем к объекту аренды
        rental.qr_code = generate_qr_code(json.dumps(qr_data, ensure_ascii=False))
        rental.qr_data = qr_data
    for rental in active_rentals:
        rental.lk_msgs = rental.lk_messages()

    overdue_rentals = rentals.filter(status='overdue')
    for rental in overdue_rentals:
        rental.lk_msgs = rental.lk_messages()


    context = {
        'user': user,
        'profile': profile,
        'active_rentals': active_rentals,
        'rentals': other_rentals,
        'overdue_rentals': overdue_rentals,
    }

    # ВАЖНО: ЭТОТ RETURN ДОЛЖЕН БЫТЬ!
    return render(request, 'storage/my-rent.html', context)


def short_link_redirect(request, code: str):
    """
    Переход по короткой ссылке:
    - увеличиваем счётчик
    - редиректим на target_path
    """
    short_link = get_object_or_404(ShortLink, code=code)

    # атомарно увеличиваем счётчик
    ShortLink.objects.filter(pk=short_link.pk).update(clicks=F("clicks") + 1)

    return redirect(short_link.target_path)


@login_required
def rent_box(request, box_id):
    box = get_object_or_404(Box, pk=box_id, is_active=True)
    base_price = box.price_per_month

    promo_result = None
    applied_promo_code = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "apply_promo":
            promo_code = request.POST.get("promo_code", "").strip()
            if promo_code:
                promo = PromoCode.objects.filter(code=promo_code).first()
                if promo:
                    if promo.is_valid_now():
                        discount = Decimal(promo.discount_percent) / 100
                        final_price = base_price * (1 - discount)
                        promo_result = {
                            "valid": True,
                            "code": promo.code,
                            "discount_percent": promo.discount_percent,
                            "base_price": base_price,
                            "final_price": final_price.quantize(Decimal("0.01")),
                        }
                        applied_promo_code = promo_code
                    else:
                        promo_result = {
                            "valid": False,
                            "error": "Промокод недействителен (истёк срок действия)",
                        }
                else:
                    promo_result = {
                        "valid": False,
                        "error": "Промокод не найден",
                    }
            else:
                promo_result = {
                    "valid": False,
                    "error": "Введите промокод",
                }

        elif action == "rent":
            promo_code = request.POST.get("promo_code", "").strip()
            contact_phone = request.POST.get("contact_phone")
            pickup_address = request.POST.get("pickup_address", "")

            final_price = base_price
            promo = None

            if promo_code:
                promo = PromoCode.objects.filter(code=promo_code).first()
                if promo and promo.is_valid_now():
                    discount = Decimal(promo.discount_percent) / 100
                    final_price = base_price * (1 - discount)

            rental = Rental.objects.create(
                user=request.user,
                box=box,
                contact_phone=contact_phone,
                pickup_address=pickup_address,
                base_price_per_month=base_price,
                final_price_per_month=final_price.quantize(Decimal("0.01")),
                promo_code=promo,
                status=Rental.Status.ACTIVE,
            )

            return redirect("storage:my_rent")

    return render(
        request,
        "storage/rent_box.html",
        {
            "box": box,
            "base_price": base_price,
            "promo_result": promo_result,
            "applied_promo_code": applied_promo_code,
        },
    )