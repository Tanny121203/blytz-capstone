from django.urls import path

from . import admin_views, views

urlpatterns = [
    path("app/orders/", views.order_list, name="order_list"),
    path("app/orders/<str:order_id>/", views.order_detail, name="order_detail"),
    path(
        "app/orders/<str:order_id>/approve-final-design/",
        views.approve_final_design,
        name="approve_final_design",
    ),
    path("staff/jobs/", views.jobs_pipeline, name="jobs_pipeline"),
    path("staff/orders/<str:order_id>/", views.staff_order_detail, name="staff_order_detail"),
    path(
        "staff/orders/<str:order_id>/previews/<str:side>/download/",
        views.download_order_preview,
        name="download_order_preview",
    ),
    path(
        "staff/orders/<str:order_id>/final-design/",
        views.upload_final_design,
        name="upload_final_design",
    ),
    path(
        "staff/orders/<str:order_id>/advance/",
        views.advance_order_phase,
        name="advance_order_phase",
    ),
    path(
        "staff/orders/<str:order_id>/payments/<int:payment_id>/review/",
        views.review_payment,
        name="review_payment",
    ),
    path(
        "staff/payment-channels/",
        admin_views.payment_channel_list,
        name="payment_channel_list",
    ),
    path(
        "staff/payment-channels/add/",
        admin_views.payment_channel_create,
        name="payment_channel_create",
    ),
    path(
        "staff/payment-channels/<int:pk>/edit/",
        admin_views.payment_channel_edit,
        name="payment_channel_edit",
    ),
    path(
        "staff/payment-channels/<int:pk>/deactivate/",
        admin_views.payment_channel_deactivate,
        name="payment_channel_deactivate",
    ),
]
