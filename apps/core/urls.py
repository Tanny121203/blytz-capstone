from django.conf import settings
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
]

if settings.DEBUG:
    urlpatterns += [
        path("dev/components/", views.components_gallery, name="dev_components"),
        path(
            "dev/components/customer/",
            views.components_gallery_customer,
            name="dev_components_customer",
        ),
        path(
            "dev/components/staff/",
            views.components_gallery_staff,
            name="dev_components_staff",
        ),
    ]
