from django.urls import path

from . import views

urlpatterns = [
    path("staff/accounting/", views.accounting_list, name="accounting_list"),
    path(
        "staff/accounting/export.csv",
        views.accounting_export_csv,
        name="accounting_export_csv",
    ),
    path(
        "staff/accounting/<str:order_id>/",
        views.accounting_detail,
        name="accounting_detail",
    ),
]
