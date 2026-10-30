from django.contrib import admin

from .models import ActivityLog, Design


class ActivityLogInline(admin.TabularInline):
    model = ActivityLog
    fk_name = "design"
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Design)
class DesignAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "garment_template",
        "garment_color",
        "updated_at",
    )
    list_filter = ("garment_template",)
    search_fields = ("title", "owner__email", "garment_template")
    autocomplete_fields = ("owner",)
    inlines = [ActivityLogInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("kind", "customer", "design", "order", "created_at")
    list_filter = ("kind",)
    search_fields = ("customer__email", "design__title", "order__order_id")
    autocomplete_fields = ("customer", "design", "order")
    readonly_fields = ("created_at",)
