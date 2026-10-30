from django.urls import path

from . import views

urlpatterns = [
    path("staff/sales/", views.sales_pipeline, name="sales_pipeline"),
    path("staff/sales/<int:lead_id>/", views.lead_detail, name="lead_detail"),
    path(
        "staff/sales/<int:lead_id>/stage/",
        views.update_lead_stage,
        name="update_lead_stage",
    ),
]
