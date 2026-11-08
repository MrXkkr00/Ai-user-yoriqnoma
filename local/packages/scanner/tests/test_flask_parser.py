"""Flask snippets: blueprints, guards, WTForms, Jinja templates and models (T29)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.api import scan

Writer = Callable[[Path, dict[str, str]], Path]

FLASK_PROJECT = {
    "requirements.txt": "flask\nflask-login\nflask-wtf\nflask-sqlalchemy\n",
    "app/__init__.py": """
from flask import Flask

from app.auth import auth_bp
from app.orders import orders_bp
from app.staff import staff_bp
from app.admin import admin_bp


def create_app():
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    app.register_blueprint(orders_bp, url_prefix="/orders")
    app.register_blueprint(staff_bp, url_prefix="/staff")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/")
    def home():
        return render_template("home.html")

    return app
""",
    "app/models.py": """
import enum

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Role(str, enum.Enum):
    CUSTOMER = "customer"
    MANAGER = "manager"
    ADMIN = "admin"


class OrderStatus(str, enum.Enum):
    NEW = "new"
    PAID = "paid"
    SHIPPED = "shipped"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    role = db.Column(db.Enum(Role), default=Role.CUSTOMER)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    phone = db.Column(db.String(20))
    status = db.Column(db.Enum(OrderStatus), default=OrderStatus.NEW)
""",
    "app/forms.py": """
from flask_wtf import FlaskForm
from flask_babel import lazy_gettext as _l
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp


class RegisterForm(FlaskForm):
    email = StringField(_l("Email"), validators=[DataRequired(), Email()])
    password = PasswordField(_l("Password"), validators=[DataRequired(), Length(min=8)])
    submit = SubmitField(_l("Sign up"))


class OrderForm(FlaskForm):
    phone = StringField("Telefon", validators=[DataRequired(), Regexp(r"^\\+998\\d{9}$")])
    submit = SubmitField("Buyurtma berish")
""",
    "app/auth.py": """
from flask import Blueprint, redirect, render_template, url_for
from flask_login import login_user

from app.forms import RegisterForm
from app.models import User, db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(email=form.email.data)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("orders.index"))
    return render_template("register.html", form=form)
""",
    "app/orders.py": """
from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.forms import OrderForm
from app.models import Order, OrderStatus, db

orders_bp = Blueprint("orders", __name__)


@orders_bp.get("/")
@login_required
def index():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template("orders/index.html", orders=orders)


@orders_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = OrderForm()
    if form.validate_on_submit():
        order = Order(user_id=current_user.id, phone=form.phone.data, status=OrderStatus.NEW)
        db.session.add(order)
        db.session.commit()
    return render_template("orders/new.html", form=form)


@orders_bp.post("/<int:order_id>/pay")
@login_required
def pay(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        abort(403)
    if order.status != OrderStatus.NEW:
        abort(400)
    order.status = OrderStatus.PAID
    db.session.commit()
    return {"ok": True}
""",
    "app/staff.py": """
from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.models import Order, OrderStatus, Role, db

staff_bp = Blueprint("staff", __name__)


@staff_bp.before_request
@login_required
def only_managers():
    if current_user.role != Role.MANAGER:
        abort(403)


@staff_bp.get("/orders")
def orders():
    return render_template("staff/orders.html", orders=Order.query.all())


@staff_bp.post("/orders/<int:order_id>/ship")
def ship(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status != OrderStatus.PAID:
        abort(409)
    order.status = OrderStatus.SHIPPED
    db.session.commit()
    return {"ok": True}
""",
    "app/admin.py": """
from functools import wraps

from flask import Blueprint, abort, render_template
from flask_login import current_user

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


@admin_bp.get("/users")
@admin_required
def users():
    return render_template("admin/users.html")
""",
    "app/templates/base.html": """<nav>
<a href="{{ url_for('home') }}">{{ _('Home') }}</a>
<a href="{{ url_for('orders.index') }}">{{ _('My orders') }}</a>
</nav>{% block content %}{% endblock %}""",
    "app/templates/register.html": """{% extends "base.html" %}{% block content %}
<form method="post">{{ form.hidden_tag() }}
{{ form.email.label }} {{ form.email(class_="input") }}
{{ form.password.label }} {{ form.password() }}
{{ form.submit() }}
</form>{% endblock %}""",
    "app/templates/orders/index.html": """{% extends "base.html" %}{% block content %}
{% for o in orders %}<form method="post" action="{{ url_for('orders.pay', order_id=o.id) }}">
<button type="submit">{{ _('Pay') }}</button></form>{% endfor %}
<a href="{{ url_for('orders.create') }}">{{ _('New order') }}</a>{% endblock %}""",
    "app/templates/orders/new.html": """{% extends "base.html" %}{% block content %}
<form method="post">{{ form.csrf_token }}{{ render_field(form.phone) }}{{ form.submit() }}</form>
{% endblock %}""",
    "app/templates/staff/orders.html": """{% extends "base.html" %}{% block content %}
{% for o in orders %}<form method="post" action="{{ url_for('staff.ship', order_id=o.id) }}">
<button>Jo'natish</button></form>{% endfor %}{% endblock %}""",
    "app/translations/uz/LC_MESSAGES/messages.po": (
        'msgid "Email"\nmsgstr "Email"\n\nmsgid "Password"\nmsgstr "Parol"\n\n'
        'msgid "Sign up"\nmsgstr "Ro\'yxatdan o\'tish"\n\nmsgid "Home"\nmsgstr "Bosh sahifa"\n\n'
        'msgid "My orders"\nmsgstr "Buyurtmalarim"\n\nmsgid "Pay"\nmsgstr "To\'lash"\n'
    ),
}


def test_flask_blueprints_guards_forms_and_statuses(tmp_path: Path, write_files: Writer) -> None:
    result = scan(write_files(tmp_path, FLASK_PROJECT), "http://127.0.0.1:5000")
    bp = result.blueprint
    kinds = {r.id: r.kind for r in bp.roles}
    pages = {p.path: (p.access, p.roles) for p in bp.pages if p.kind == "page"}
    excluded = {p.path for p in bp.excluded}

    assert "flask" in result.stacks
    assert kinds == {"guest": "guest", "customer": "role", "manager": "role", "admin": "excluded"}
    assert bp.role("customer").self_signup  # type: ignore[union-attr]
    assert pages["/"][0] == "guest" and pages["/register"][0] == "guest"
    assert pages["/orders/"] == ("roles", ["customer", "manager"])
    assert pages["/staff/orders"] == ("roles", ["manager"])  # before_request role check
    assert "/admin/users" in excluded
    order = bp.entity("order")
    assert order is not None and order.owner_field == "user_id" and "phone" in order.pii_fields
    reach = {s.value: s.reachable_by for s in order.statuses}
    assert reach == {
        "new": ["customer", "manager"],
        "paid": ["customer", "manager"],
        "shipped": ["manager"],
    }
    flows = {f.id: f for f in bp.flows}
    register = flows["customer.register"]
    assert [s.target.label for s in register.steps if s.action == "fill" and s.target] == [
        "Email",
        "Parol",
    ]
    assert register.steps[-1].target is not None
    assert register.steps[-1].target.name == "Ro'yxatdan o'tish"
    assert flows["manager.order.ship"].needs_status == ["paid"]
    assert "customer.order.pay" in flows["manager.order.ship"].requires
    forms = {f.api: f for f in bp.forms}
    phone = forms["POST /orders/new"].fields[0]
    assert phone.label == "Telefon" and phone.rules == "regex:^\\+998\\d{9}$"
    nav = {n["path"]: n["label"] for n in bp.nav}
    assert nav["/orders/"] == "Buyurtmalarim"
