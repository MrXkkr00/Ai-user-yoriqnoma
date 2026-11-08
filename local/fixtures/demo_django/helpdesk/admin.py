from django.contrib import admin

from helpdesk.models import Ticket, User

admin.site.register(User)
admin.site.register(Ticket)
