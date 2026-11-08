from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from helpdesk.decorators import role_required
from helpdesk.forms import ProfileForm, ReplyForm, SignUpForm, TicketForm
from helpdesk.models import Reply, Ticket, User


class HomeView(TemplateView):
    template_name = "helpdesk/home.html"


def signup(request):
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.role = User.Role.CUSTOMER
        user.save()
        login(request, user)
        return redirect("helpdesk:ticket_list")
    return render(request, "registration/signup.html", {"form": form})


class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = "helpdesk/ticket_list.html"

    def get_queryset(self):
        return Ticket.objects.filter(owner=self.request.user)


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketForm
    template_name = "helpdesk/ticket_form.html"

    def get_success_url(self):
        return reverse("helpdesk:ticket_detail", args=[self.object.pk])

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.status = Ticket.Status.OPEN
        return super().form_valid(form)


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, owner=request.user)
    return render(request, "helpdesk/ticket_detail.html", {"ticket": ticket})


@login_required
@require_POST
def ticket_close(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, owner=request.user)
    if ticket.status != Ticket.Status.ANSWERED:
        return redirect("helpdesk:ticket_detail", pk=pk)
    ticket.status = Ticket.Status.CLOSED
    ticket.save()
    return redirect("helpdesk:ticket_detail", pk=pk)


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "helpdesk/profile.html"
    success_url = reverse_lazy("helpdesk:profile")

    def get_object(self):
        return self.request.user


@role_required("support")
def support_queue(request):
    tickets = Ticket.objects.filter(status=Ticket.Status.OPEN)
    return render(request, "helpdesk/support_queue.html", {"tickets": tickets})


@role_required("support")
def support_reply(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    form = ReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if ticket.status != Ticket.Status.OPEN:
            return redirect("helpdesk:support_queue")
        Reply.objects.create(ticket=ticket, author=request.user, text=form.cleaned_data["text"])
        ticket.status = Ticket.Status.ANSWERED
        ticket.save()
        return redirect("helpdesk:support_queue")
    return render(request, "helpdesk/support_reply.html", {"ticket": ticket, "form": form})


@staff_member_required
def panel_users(request):
    return render(request, "panel/users.html", {"users": User.objects.all()})


@staff_member_required
@require_POST
def panel_archive(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    ticket.status = Ticket.Status.ARCHIVED
    ticket.save()
    return redirect("panel_users")
