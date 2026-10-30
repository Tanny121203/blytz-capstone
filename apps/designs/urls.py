from django.urls import path

from . import views

urlpatterns = [
    path("app/", views.dashboard, name="app_home"),
    path("app/designs/", views.design_list, name="design_list"),
    path("app/designs/new/", views.design_create, name="design_create"),
    path("app/designs/<int:pk>/", views.design_detail, name="design_detail"),
    path("app/designs/<int:pk>/editor/", views.design_editor, name="design_editor"),
    path("app/designs/<int:pk>/save/", views.design_save, name="design_save"),
    path("app/designs/<int:pk>/submit/", views.design_submit, name="design_submit"),
    path(
        "app/designs/<int:pk>/ai/suggest/",
        views.design_ai_suggest,
        name="design_ai_suggest",
    ),
]
