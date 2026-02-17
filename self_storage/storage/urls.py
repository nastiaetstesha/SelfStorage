from django.urls import path
from . import views

app_name = "storage"

urlpatterns = [
    path("", views.index, name="index"),
    path("faq/", views.faq, name="faq"),
    path("boxes/", views.boxes, name="boxes"),
    path("my-rent/", views.my_rent, name="my_rent"),
]
