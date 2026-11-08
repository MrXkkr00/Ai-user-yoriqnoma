from django.urls import path

from domains import views

app_name = "domains"

urlpatterns = [
    path("", views.domain_list, name="list"),
    path("<int:pk>/verify/", views.domain_verify, name="verify"),
    path("<int:pk>/delete/", views.domain_delete, name="delete"),
]
