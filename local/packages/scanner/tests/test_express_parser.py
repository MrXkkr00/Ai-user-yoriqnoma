"""Express snippets: routers across files, middleware guards, controllers, Mongoose (T29)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.api import scan

Writer = Callable[[Path, dict[str, str]], Path]

EXPRESS_PROJECT = {
    "package.json": '{"dependencies": {"express": "^4.19.2", "mongoose": "^8.0.0"}}',
    "server/app.js": """
const express = require('express');
const authRoutes = require('./routes/auth');
const orderRoutes = require('./routes/orders');
const staffRoutes = require('./routes/staff');
const adminRoutes = require('./routes/admin');
const { requireAuth } = require('./middleware/auth');

const app = express();
app.use(express.json());
app.use('/api/auth', authRoutes);
app.use('/api/orders', requireAuth, orderRoutes);
app.use('/api/staff', staffRoutes);
app.use('/api/admin', adminRoutes);
app.get('/', (req, res) => res.render('home'));

module.exports = app;
""",
    "server/middleware/auth.js": """
const jwt = require('jsonwebtoken');

function requireAuth(req, res, next) {
  const token = req.headers.authorization;
  if (!token) return res.status(401).json({ error: 'auth' });
  req.user = jwt.verify(token, process.env.SECRET);
  next();
}

const requireRole = (...roles) => (req, res, next) => {
  if (!roles.includes(req.user.role)) return res.status(403).end();
  next();
};

module.exports = { requireAuth, requireRole };
""",
    "server/models/User.js": """
const mongoose = require('mongoose');

const UserSchema = new mongoose.Schema({
  email: { type: String, required: true },
  phone: String,
  role: { type: String, enum: ['customer', 'manager', 'admin'], default: 'customer' },
});

module.exports = mongoose.model('User', UserSchema);
""",
    "server/models/Order.js": """
const mongoose = require('mongoose');

const OrderSchema = new mongoose.Schema({
  user: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  address: String,
  status: { type: String, enum: ['new', 'paid', 'shipped'], default: 'new' },
});

module.exports = mongoose.model('Order', OrderSchema);
""",
    "server/routes/auth.js": """
const router = require('express').Router();
const User = require('../models/User');

router.post('/register', async (req, res) => {
  const user = await User.create({ email: req.body.email, phone: req.body.phone });
  res.status(201).json(user);
});

router.post('/login', async (req, res) => res.json({ ok: true }));

module.exports = router;
""",
    "server/routes/orders.js": """
const express = require('express');
const ctrl = require('../controllers/orders');

const router = express.Router();
router.route('/').get(ctrl.list).post(ctrl.create);
router.post('/:id/pay', ctrl.pay);

module.exports = router;
""",
    "server/controllers/orders.js": """
const Order = require('../models/Order');

exports.list = async (req, res) => res.json(await Order.find({ user: req.user.id, status: 'new' }));

exports.create = async (req, res) => {
  const order = await Order.create({ user: req.user.id, address: req.body.address, status: 'new' });
  res.status(201).json(order);
};

exports.pay = async (req, res) => {
  const order = await Order.findById(req.params.id);
  if (order.user.toString() !== req.user.id) return res.status(403).end();
  if (order.status !== 'new') return res.status(400).json({ error: 'status' });
  order.status = 'paid';
  await order.save();
  res.json(order);
};
""",
    "server/routes/staff.js": """
const router = require('express').Router();
const { requireAuth, requireRole } = require('../middleware/auth');
const Order = require('../models/Order');

router.use(requireAuth, requireRole('manager'));
router.get('/orders', async (req, res) => res.json(await Order.find()));
router.patch('/orders/:id/ship', async (req, res) => {
  const order = await Order.findById(req.params.id);
  if (order.status !== 'paid') return res.status(409).end();
  await Order.updateOne({ _id: order.id }, { status: 'shipped' });
  res.json({ ok: true });
});

module.exports = router;
""",
    "server/routes/admin.js": """
const router = require('express').Router();
const { requireAuth, requireRole } = require('../middleware/auth');

router.get('/users', requireAuth, requireRole('admin'), (req, res) => res.json([]));

module.exports = router;
""",
    "views/home.ejs": """<form method="post" action="/subscribe">
<label for="e"><%= __('Email') %></label><input id="e" name="email" type="email" required>
<button>Obuna bo'lish</button></form>""",
}


def test_express_routers_guards_controllers_and_models(tmp_path: Path, write_files: Writer) -> None:
    result = scan(write_files(tmp_path, EXPRESS_PROJECT), "http://127.0.0.1:3000")
    bp = result.blueprint
    kinds = {r.id: r.kind for r in bp.roles}
    api = {(p.path, m): p for p in bp.pages if p.kind == "api" for m in p.methods}
    excluded = {p.path for p in bp.excluded}

    assert "express" in result.stacks
    assert kinds == {"guest": "guest", "customer": "role", "manager": "role", "admin": "excluded"}
    assert bp.role("customer").self_signup  # type: ignore[union-attr]
    assert api[("/api/auth/register", "POST")].access == "guest"
    assert api[("/api/orders", "GET")].roles == ["customer", "manager"]
    assert api[("/api/orders", "POST")].roles == ["customer", "manager"]
    assert api[("/api/orders/:id/pay", "POST")].roles == ["customer", "manager"]
    assert api[("/api/staff/orders", "GET")].roles == ["manager"]
    assert api[("/api/staff/orders/:id/ship", "PATCH")].roles == ["manager"]
    assert "/api/admin/users" in excluded
    order = bp.entity("order")
    assert order is not None and order.owner_field == "user" and "address" in order.pii_fields
    assert {"list", "create", "pay", "ship"} <= set(order.actions)
    reach = {s.value: s.reachable_by for s in order.statuses}
    assert reach == {
        "new": ["customer", "manager"],
        "paid": ["customer", "manager"],
        "shipped": ["manager"],
    }
    home = next(p for p in bp.pages if p.kind == "page" and p.path == "/")
    assert home.access == "guest"
    form = next(f for f in bp.forms if f.api == "POST /subscribe")
    assert form.fields[0].label == "Email" and form.fields[0].type == "email"
