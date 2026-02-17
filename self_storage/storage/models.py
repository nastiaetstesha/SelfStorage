from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


PRICE_PER_M3_PER_MONTH = Decimal("750.00")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        abstract = True


class Warehouse(TimeStampedModel):
    """Склад (точка хранения)."""
    title = models.CharField("Название", max_length=200)
    city = models.CharField("Город", max_length=120, default="Москва")
    address = models.CharField("Адрес", max_length=300)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    work_hours = models.CharField("Часы работы", max_length=120, blank=True, default="Ежедневно 9:00–21:00")
    is_active = models.BooleanField("Активен", default=True)
    photo = models.ImageField("Фото склада", upload_to="warehouses/", blank=True, null=True)

    class Meta:
        verbose_name = "Склад"
        verbose_name_plural = "Склады"
        ordering = ["city", "title"]

    def __str__(self) -> str:
        return f"{self.title} — {self.city}"

    def available_boxes_count(self) -> int:
        """
        Сколько боксов доступно (не заняты активной/просроченной арендой).
        """
        busy_box_ids = Rental.objects.filter(
            status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE]
        ).values_list("box_id", flat=True)
        return self.boxes.filter(is_active=True).exclude(id__in=busy_box_ids).count()

    def total_boxes_count(self) -> int:
        return self.boxes.filter(is_active=True).count()


class Box(TimeStampedModel):
    """Бокс/ячейка на складе с размерами."""
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="boxes", verbose_name="Склад")
    code = models.CharField("Код бокса", max_length=50)
    length_m = models.DecimalField("Длина, м", max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    width_m = models.DecimalField("Ширина, м", max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    height_m = models.DecimalField("Высота, м", max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Бокс"
        verbose_name_plural = "Боксы"
        unique_together = [("warehouse", "code")]
        ordering = ["warehouse__title", "code"]

    def __str__(self) -> str:
        return f"{self.warehouse.title}: {self.code}"

    @property
    def volume_m3(self) -> Decimal:
        return (self.length_m * self.width_m * self.height_m).quantize(Decimal("0.01"))

    @property
    def price_per_month(self) -> Decimal:
        return (self.volume_m3 * PRICE_PER_M3_PER_MONTH).quantize(Decimal("0.01"))


class StorageRule(TimeStampedModel):
    """Правила хранения: разрешено/запрещено (быстрый ответ про жидкости и т.п.)."""
    class RuleType(models.TextChoices):
        ALLOWED = "allowed", "Разрешено"
        FORBIDDEN = "forbidden", "Запрещено"

    rule_type = models.CharField("Тип", max_length=20, choices=RuleType.choices)
    title = models.CharField("Пункт", max_length=200)
    is_active = models.BooleanField("Активно", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Правило хранения"
        verbose_name_plural = "Правила хранения"
        ordering = ["sort_order", "rule_type", "title"]

    def __str__(self) -> str:
        return f"{self.get_rule_type_display()}: {self.title}"


class PrivacyPolicyDocument(TimeStampedModel):
    """PDF документ для согласия на обработку ПД."""
    title = models.CharField("Название", max_length=200, default="Согласие на обработку персональных данных")
    file = models.FileField("PDF", upload_to="documents/privacy/")
    is_active = models.BooleanField("Активный", default=True)

    class Meta:
        verbose_name = "Документ ПД"
        verbose_name_plural = "Документы ПД"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class PromoCode(TimeStampedModel):
    """Промокод (единственная фича из доп. списка)."""
    code = models.CharField("Код", max_length=40, unique=True)
    discount_percent = models.PositiveSmallIntegerField(
        "Скидка, %",
        validators=[MinValueValidator(1), MaxValueValidator(90)],
    )
    starts_at = models.DateTimeField("Начало")
    ends_at = models.DateTimeField("Конец")
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} (-{self.discount_percent}%)"

    def is_valid_now(self) -> bool:
        now = timezone.now()
        return self.is_active and self.starts_at <= now <= self.ends_at


class AdCampaign(TimeStampedModel):
    """Код рекламы, чтобы посчитать количество заказов."""
    title = models.CharField("Название", max_length=200, blank=True)
    code = models.CharField("Код кампании", max_length=80, unique=True)

    class Meta:
        verbose_name = "Рекламная кампания"
        verbose_name_plural = "Рекламные кампании"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.code


class UserProfile(TimeStampedModel):
    """Профиль для личного кабинета (телефон + аватар как на макете)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField("Телефон", max_length=30, blank=True)
    avatar = models.ImageField("Аватар", upload_to="avatars/", blank=True, null=True)

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self) -> str:
        return f"Профиль: {self.user}"


class Rental(TimeStampedModel):
    """
    Аренда бокса.
    - дефолт 1 месяц
    - хранит адрес забора (если бесплатный вывоз)
    - хранит QR-токен (как минимум токен; QR картинку можно генерировать позже)
    - статусы: активна / просрочена / закрыта / потеряна
    """
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        OVERDUE = "overdue", "Просрочена"
        CLOSED = "closed", "Закрыта"
        LOST = "lost", "Потеряна (не забрали 6 месяцев)"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rentals", verbose_name="Пользователь")
    box = models.ForeignKey(Box, on_delete=models.PROTECT, related_name="rentals", verbose_name="Бокс")

    start_date = models.DateField("Начало аренды", default=timezone.localdate)
    end_date = models.DateField("Конец аренды", blank=True, null=True)

    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Доставка
    pickup_from_home = models.BooleanField("Бесплатный вывоз из дома", default=True)
    pickup_address = models.CharField("Адрес забора", max_length=300, blank=True)

    # Контакты (чтобы доставщик видел)
    contact_name = models.CharField("Имя для связи", max_length=200, blank=True)
    contact_phone = models.CharField("Телефон для связи", max_length=30)

    # Consent
    personal_data_consent = models.BooleanField("Согласие на ПД", default=False)
    consent_document = models.ForeignKey(
        PrivacyPolicyDocument,
        on_delete=models.PROTECT,
        verbose_name="Документ ПД",
        null=True,
        blank=True,
    )

    # Реклама/промокод
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Промокод")
    ad_campaign = models.ForeignKey(AdCampaign, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Кампания")

    # Доступ к боксу
    access_token = models.UUIDField("Токен доступа", default=uuid.uuid4, editable=False)

    # Куда “складировать” просрочку: 6 месяцев после end_date => LOST
    overdue_grace_months = models.PositiveSmallIntegerField("Месяцев хранения после срока", default=6)

    # Денежка
    base_price_per_month = models.DecimalField("Цена/мес без скидки", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    final_price_per_month = models.DecimalField("Цена/мес со скидкой", max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = "Аренда"
        verbose_name_plural = "Аренды"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "end_date"]),
        ]

    def __str__(self) -> str:
        return f"Аренда {self.user} — {self.box} ({self.get_status_display()})"

    def clean(self):
        # ПД: нельзя оформлять “боевую” аренду без согласия
        if not self.personal_data_consent:
            raise ValidationError("Нельзя оформить аренду без согласия на обработку персональных данных.")
        if self.personal_data_consent and not self.consent_document:
            raise ValidationError("При согласии на ПД нужно указать активный документ ПД (PDF).")

        # Если включен вывоз — адрес обязателен
        if self.pickup_from_home and not self.pickup_address:
            raise ValidationError("Для бесплатного вывоза из дома нужен адрес забора.")

        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("Дата окончания не может быть раньше даты начала.")

        # Нельзя назначить бокс, который занят другой активной/просроченной арендой
        conflict = Rental.objects.filter(
            box=self.box,
            status__in=[Rental.Status.ACTIVE, Rental.Status.OVERDUE],
        )
        if self.pk:
            conflict = conflict.exclude(pk=self.pk)
        if conflict.exists():
            raise ValidationError("Этот бокс уже занят активной/просроченной арендой.")

    def _default_end_date(self) -> timezone.datetime.date:
        # MVP: 1 месяц ~= 30 дней (без зависимостей)
        return self.start_date + timedelta(days=30)

    def recalc_prices(self):
        base = self.box.price_per_month
        self.base_price_per_month = base

        discount = Decimal("0.00")
        if self.promo_code and self.promo_code.is_valid_now():
            discount = Decimal(self.promo_code.discount_percent) / Decimal("100")

        self.final_price_per_month = (base * (Decimal("1.00") - discount)).quantize(Decimal("0.01"))

    def update_overdue_statuses(self):
        """
        - если прошёл end_date => OVERDUE
        - если прошло end_date + 6 месяцев => LOST
        """
        if not self.end_date:
            return

        today = timezone.localdate()
        if self.status in [self.Status.CLOSED, self.Status.LOST]:
            return

        if today > self.end_date:
            self.status = self.Status.OVERDUE

            lost_date = self.end_date + timedelta(days=30 * int(self.overdue_grace_months))
            if today > lost_date:
                self.status = self.Status.LOST

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self._default_end_date()
        self.recalc_prices()
        self.update_overdue_statuses()
        super().save(*args, **kwargs)


class DeliveryTask(TimeStampedModel):
    """
    Минимальная сущность “задача доставщику”:
    чтобы заказчик видел “куда ехать” и телефон.
    """
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Выполнена"
        CANCELED = "canceled", "Отменена"

    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name="delivery_tasks", verbose_name="Аренда")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    from_address = models.CharField("Откуда", max_length=300, blank=True)
    to_address = models.CharField("Куда", max_length=300, blank=True)
    planned_date = models.DateField("Плановая дата", null=True, blank=True)

    class Meta:
        verbose_name = "Задача доставки"
        verbose_name_plural = "Задачи доставки"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Доставка ({self.get_status_display()}) — {self.rental}"


class EmailNotification(TimeStampedModel):
    """
    Лог email-уведомлений по аренде:
    - 30/14/7/3 дня до конца
    - после просрочки: письмо “что будет” + ежемесячные напоминания
    - письмо с QR/адресом выдачи (можно хранить как тип)
    """
    class Kind(models.TextChoices):
        BEFORE_30 = "before_30", "За 30 дней"
        BEFORE_14 = "before_14", "За 14 дней"
        BEFORE_7 = "before_7", "За 7 дней"
        BEFORE_3 = "before_3", "За 3 дня"
        OVERDUE_INFO = "overdue_info", "Просрочка: что будет"
        OVERDUE_MONTHLY = "overdue_monthly", "Просрочка: ежемесячно"
        PICKUP_QR = "pickup_qr", "Выдача: QR"
        PARTIAL_PICKUP_OK = "partial_pickup_ok", "Частичный вывоз разрешён"

    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name="emails", verbose_name="Аренда")
    kind = models.CharField("Тип", max_length=30, choices=Kind.choices)
    to_email = models.EmailField("Кому", blank=True, null=True)
    subject = models.CharField("Тема", max_length=200)
    body = models.TextField("Текст")
    sent_at = models.DateTimeField("Отправлено", null=True, blank=True)
    is_sent = models.BooleanField("Отправлено", default=False)

    class Meta:
        verbose_name = "Email-уведомление"
        verbose_name_plural = "Email-уведомления"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.rental_id}"
