from django.contrib import admin
from django.db.models import Count

from .models import (
    AdCampaign,
    Box,
    DeliveryTask,
    EmailNotification,
    PrivacyPolicyDocument,
    PromoCode,
    Rental,
    StorageRule,
    UserProfile,
    Warehouse,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "address", "is_active", "total_boxes", "available_boxes")
    list_filter = ("is_active", "city")
    search_fields = ("title", "address", "city")

    def total_boxes(self, obj: Warehouse):
        return obj.total_boxes_count()
    total_boxes.short_description = "Всего боксов"

    def available_boxes(self, obj: Warehouse):
        return obj.available_boxes_count()
    available_boxes.short_description = "Свободно"


@admin.register(Box)
class BoxAdmin(admin.ModelAdmin):
    list_display = ("code", "warehouse", "dims", "volume_m3", "price_per_month", "is_active")
    list_filter = ("is_active", "warehouse__city", "warehouse")
    search_fields = ("code", "warehouse__title", "warehouse__address")

    def dims(self, obj: Box):
        return f"{obj.length_m}×{obj.width_m}×{obj.height_m} м"
    dims.short_description = "Размеры"

    def volume_m3(self, obj: Box):
        return obj.volume_m3
    volume_m3.short_description = "Объём, м³"

    def price_per_month(self, obj: Box):
        return obj.price_per_month
    price_per_month.short_description = "Цена/мес, ₽"


@admin.register(StorageRule)
class StorageRuleAdmin(admin.ModelAdmin):
    list_display = ("rule_type", "title", "is_active", "sort_order")
    list_filter = ("rule_type", "is_active")
    search_fields = ("title",)
    ordering = ("sort_order",)


@admin.register(PrivacyPolicyDocument)
class PrivacyPolicyDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title",)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_percent", "starts_at", "ends_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code",)


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "orders_count", "created_at")
    search_fields = ("code", "title")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_orders_count=Count("rental"))

    def orders_count(self, obj):
        return getattr(obj, "_orders_count", 0)
    orders_count.short_description = "Заказов"


class DeliveryTaskInline(admin.TabularInline):
    model = DeliveryTask
    extra = 0


class EmailNotificationInline(admin.TabularInline):
    model = EmailNotification
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    inlines = (DeliveryTaskInline, EmailNotificationInline)

    list_display = (
        "id",
        "user",
        "box",
        "status",
        "start_date",
        "end_date",
        "final_price_per_month",
        "pickup_from_home",
        "contact_phone",
        "created_at",
    )
    list_filter = ("status", "pickup_from_home", "box__warehouse__city", "box__warehouse")
    search_fields = ("user__username", "user__email", "contact_phone", "pickup_address", "box__code")
    readonly_fields = ("access_token", "base_price_per_month", "final_price_per_month", "created_at", "updated_at")

    fieldsets = (
        ("Основное", {"fields": ("user", "box", "status", "start_date", "end_date")}),
        ("Цена", {"fields": ("promo_code", "base_price_per_month", "final_price_per_month")}),
        ("Контакты", {"fields": ("contact_name", "contact_phone")}),
        ("Вывоз из дома", {"fields": ("pickup_from_home", "pickup_address")}),
        ("Реклама", {"fields": ("ad_campaign",)}),
        ("Персональные данные", {"fields": ("personal_data_consent", "consent_document")}),
        ("Доступ", {"fields": ("access_token",)}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "created_at")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(DeliveryTask)
class DeliveryTaskAdmin(admin.ModelAdmin):
    list_display = ("rental", "status", "planned_date", "from_address", "to_address", "created_at")
    list_filter = ("status", "planned_date")
    search_fields = ("rental__user__username", "rental__contact_phone", "from_address", "to_address")


@admin.register(EmailNotification)
class EmailNotificationAdmin(admin.ModelAdmin):
    list_display = ("rental", "kind", "to_email", "is_sent", "sent_at", "created_at")
    list_filter = ("kind", "is_sent")
    search_fields = ("to_email", "subject", "rental__user__email")
