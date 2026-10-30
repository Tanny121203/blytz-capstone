from django.contrib import admin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("customer", "order", "stage", "created_at")
    list_filter = ("stage",)
    search_fields = ("customer__email", "order__order_id")
    autocomplete_fields = ("customer", "order")
    readonly_fields = ("created_at",)
