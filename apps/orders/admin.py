from django.contrib import admin

from .models import Order, OrderPhaseChange, Payment, PaymentChannel


@admin.register(PaymentChannel)
class PaymentChannelAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "kind",
        "account_name",
        "account_number",
        "is_active",
    )
    list_filter = ("kind", "is_active")
    search_fields = ("display_name", "account_name", "account_number")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id",
        "customer",
        "design",
        "status",
        "agreed_total",
        "payment_status_display",
        "balance_display",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("order_id", "customer__email", "notes")
    readonly_fields = (
        "order_id",
        "created_at",
        "final_design_version",
        "final_design_uploaded_at",
        "approved_version",
        "approved_at",
    )
    inlines = [PaymentInline]
    autocomplete_fields = ("customer", "design")

    @admin.display(description="Payment status")
    def payment_status_display(self, obj):
        return obj.payment_status

    @admin.display(description="Balance")
    def balance_display(self, obj):
        return obj.balance


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "channel",
        "amount_claimed",
        "status",
        "created_at",
    )
    list_filter = ("status", "channel")
    search_fields = ("order__order_id",)
    autocomplete_fields = ("order", "channel", "reviewed_by", "recorded_by")
    readonly_fields = ("created_at", "reviewed_at")


@admin.register(OrderPhaseChange)
class OrderPhaseChangeAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "from_status",
        "to_status",
        "changed_by",
        "changed_at",
    )
    list_filter = ("from_status", "to_status")
    search_fields = ("order__order_id",)
    autocomplete_fields = ("order", "changed_by")
    readonly_fields = ("changed_at",)
