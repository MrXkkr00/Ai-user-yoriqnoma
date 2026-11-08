from django.urls import path, re_path

from helpdesk import views

app_name = "helpdesk"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("accounts/signup/", views.signup, name="signup"),
    path("tickets/", views.TicketListView.as_view(), name="ticket_list"),
    path("tickets/new/", views.TicketCreateView.as_view(), name="ticket_create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("tickets/<int:pk>/close/", views.ticket_close, name="ticket_close"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("support/", views.support_queue, name="support_queue"),
    re_path(r"^support/tickets/(?P<pk>\d+)/reply/$", views.support_reply, name="support_reply"),
    path("panel/users/", views.panel_users, name="panel_users"),
    path("panel/tickets/<int:pk>/archive/", views.panel_archive, name="panel_archive"),
]
