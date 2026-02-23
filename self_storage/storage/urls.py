from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "storage"

urlpatterns = [
    path("", views.index, name="index"),
    path("faq/", views.faq, name="faq"),
    path("boxes/", views.boxes, name="boxes"),
    path("my-rent/", views.my_rent, name="my_rent"),
    path("register/", views.register, name="register"),
    path("login/", views.login_redirect, name="login"),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="storage:index"),
        name="logout",
    ),
    path("s/<str:code>/", views.short_link_redirect, name="short_link"),
    path("rent/<int:box_id>/", views.rent_box, name="rent_box"),
]
