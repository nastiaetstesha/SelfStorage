from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.db.models import Exists, OuterRef
from django.utils import timezone

from storage.models import Rental, EmailNotification, PRICE_PER_M3_PER_MONTH


OVERDUE_TARIFF_MULTIPLIER = Decimal("1.10")  # +10%


class Command(BaseCommand):
    help = "Send rental reminder emails (before end, overdue info, monthly overdue reminders)."

    def handle(self, *args, **options):
        today = timezone.localdate()

        sent = 0
        sent += self._send_before_end(today)
        sent += self._send_overdue_info(today)
        sent += self._send_overdue_monthly(today)

        self.stdout.write(self.style.SUCCESS(f"Done. Emails created/sent: {sent}"))

    def _send_before_end(self, today):
        # напоминания: за 30/14/7/3 дня
        rules = [
            (30, EmailNotification.Kind.BEFORE_30),
            (14, EmailNotification.Kind.BEFORE_14),
            (7, EmailNotification.Kind.BEFORE_7),
            (3, EmailNotification.Kind.BEFORE_3),
        ]

        total = 0
        for days, kind in rules:
            target_end = today + timedelta(days=days)

            # аренды, которые заканчиваются ровно в этот день
            qs = Rental.objects.filter(
                status__in=[Rental.Status.ACTIVE],
                end_date=target_end,
            )

            # не шлём, если такое уведомление уже было
            already_sent = EmailNotification.objects.filter(
                rental_id=OuterRef("pk"),
                kind=kind,
            )
            qs = qs.annotate(_already=Exists(already_sent)).filter(_already=False)

            for rental in qs.select_related("user", "box__warehouse"):
                to_email = getattr(rental.user, "email", "") if rental.user else ""
                if not to_email:
                    continue

                subject = f"SelfStorage: срок аренды подходит к концу (через {days} дн.)"
                body = self._render_before_end_body(rental, days)

                self._create_and_send(kind, rental, to_email, subject, body)
                total += 1

        return total

    def _send_overdue_info(self, today):
        # письмо "что будет" — отправляем один раз, когда аренда стала OVERDUE
        qs = Rental.objects.filter(status=Rental.Status.OVERDUE)

        already_sent = EmailNotification.objects.filter(
            rental_id=OuterRef("pk"),
            kind=EmailNotification.Kind.OVERDUE_INFO,
        )
        qs = qs.annotate(_already=Exists(already_sent)).filter(_already=False)

        total = 0
        for rental in qs.select_related("user", "box__warehouse"):
            to_email = getattr(rental.user, "email", "") if rental.user else ""
            if not to_email:
                continue

            subject = "SelfStorage: вы не забрали вещи в срок — что дальше"
            body = self._render_overdue_info_body(rental)

            self._create_and_send(EmailNotification.Kind.OVERDUE_INFO, rental, to_email, subject, body)
            total += 1

        return total

    def _send_overdue_monthly(self, today):
        # раз в месяц после просрочки
        qs = Rental.objects.filter(status=Rental.Status.OVERDUE)

        # отправляем, если прошло >= 30 дней с end_date и дальше кратно 30
        # MVP (без calendar-месяцев): (today - end_date).days % 30 == 0 и > 0
        total = 0
        for rental in qs.select_related("user", "box__warehouse"):
            if not rental.end_date:
                continue
            days_overdue = (today - rental.end_date).days
            if days_overdue <= 0:
                continue
            if days_overdue % 30 != 0:
                continue

            # не дублируем: один раз на каждый "месяц просрочки"
            # например, month_index = 1,2,3...
            month_index = days_overdue // 30
            subject = f"SelfStorage: напоминание — вещи не забраны ({month_index} мес. просрочки)"
            body = self._render_overdue_monthly_body(rental, month_index)

            # чтобы не дублировать — кладём marker в тему + kind.
            already = EmailNotification.objects.filter(
                rental=rental,
                kind=EmailNotification.Kind.OVERDUE_MONTHLY,
                subject=subject,
            ).exists()
            if already:
                continue

            to_email = getattr(rental.user, "email", "") if rental.user else ""
            if not to_email:
                continue

            self._create_and_send(EmailNotification.Kind.OVERDUE_MONTHLY, rental, to_email, subject, body)
            total += 1

        return total

    def _create_and_send(self, kind, rental, to_email, subject, body):
        email_log = EmailNotification.objects.create(
            rental=rental,
            kind=kind,
            to_email=to_email,
            subject=subject,
            body=body,
            sent_at=timezone.now(),
            is_sent=True,
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=None,
            recipient_list=[to_email],
            fail_silently=False,
        )
        return email_log

    def _render_before_end_body(self, rental, days):
        warehouse = rental.box.warehouse
        return (
            f"Здравствуйте!\n\n"
            f"Напоминаем: срок аренды бокса подходит к концу через {days} дн.\n\n"
            f"Склад: {warehouse.city}, {warehouse.address}\n"
            f"Бокс: {rental.box.code}\n"
            f"Дата окончания: {rental.end_date}\n\n"
            f"Если вы уже забрали вещи — просто игнорируйте это письмо.\n"
            f"Спасибо!\n"
        )

    def _render_overdue_info_body(self, rental):
        warehouse = rental.box.warehouse
        overdue_price = (rental.final_price_per_month * OVERDUE_TARIFF_MULTIPLIER).quantize(Decimal("0.01"))
        return (
            f"Здравствуйте!\n\n"
            f"Срок аренды вашего бокса истёк {rental.end_date}, а вещи ещё не забраны.\n\n"
            f"Что будет дальше:\n"
            f"1) Мы продолжим хранить вещи ещё {rental.overdue_grace_months} месяцев.\n"
            f"2) На период просрочки действует повышенный тариф: {overdue_price} ₽/мес.\n"
            f"3) Если вещи не будут забраны в течение {rental.overdue_grace_months} месяцев после даты окончания,\n"
            f"   аренда будет помечена как «Потеряна».\n\n"
            f"Склад: {warehouse.city}, {warehouse.address}\n"
            f"Бокс: {rental.box.code}\n\n"
            f"Если хотите закрыть аренду — приезжайте на склад и заберите вещи.\n"
        )

    def _render_overdue_monthly_body(self, rental, month_index):
        warehouse = rental.box.warehouse
        return (
            f"Здравствуйте!\n\n"
            f"Напоминание: ваши вещи всё ещё не забраны (прошло {month_index} мес. после окончания аренды).\n\n"
            f"Склад: {warehouse.city}, {warehouse.address}\n"
            f"Бокс: {rental.box.code}\n"
            f"Дата окончания аренды: {rental.end_date}\n\n"
            f"Пожалуйста, заберите вещи при первой возможности.\n"
        )
