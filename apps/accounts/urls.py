from django.urls import path

from . import admin_views, views

urlpatterns = [
    path("staff/", views.staff_home, name="staff_home"),
    path("staff/admin-only/", views.staff_admin_only, name="staff_admin_only"),
    path("app/profile/", views.profile, name="account_profile"),
    path("staff/users/", admin_views.user_manage_list, name="user_manage_list"),
    path("staff/users/add/", admin_views.user_create_staff, name="user_create_staff"),
    path("staff/users/<int:pk>/", admin_views.user_edit, name="user_edit"),
]
