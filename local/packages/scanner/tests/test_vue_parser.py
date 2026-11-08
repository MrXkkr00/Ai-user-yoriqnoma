"""Vue snippets: Vue Router meta guards, nested routes, SFC forms and handlers (T29)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.api import scan

Writer = Callable[[Path, dict[str, str]], Path]

API = {
    "server/package.json": '{"dependencies": {"express": "^4.19.2", "mongoose": "^8.0.0"}}',
    "server/app.js": """
const express = require('express');
const { requireAuth, requireRole } = require('./auth');
const Order = require('./order');
const User = require('./user');
const app = express();

app.post('/api/register', async (req, res) => res.json(await User.create(req.body)));
app.post('/api/login', async (req, res) => res.json({}));
app.get('/api/orders', requireAuth, async (req, res) =>
  res.json(await Order.find({ user: req.user.id })));
app.post('/api/orders', requireAuth, async (req, res) =>
  res.json(await Order.create({ user: req.user.id, address: req.body.address, status: 'new' })));
app.get('/api/staff/orders', requireAuth, requireRole('manager'), async (req, res) =>
  res.json(await Order.find()));
app.post('/api/staff/orders/:id/ship', requireAuth, requireRole('manager'), async (req, res) => {
  const order = await Order.findById(req.params.id);
  if (order.status !== 'new') return res.status(409).end();
  order.status = 'shipped';
  await order.save();
  res.json(order);
});
module.exports = app;
""",
    "server/auth.js": """
function requireAuth(req, res, next) {
  if (!req.user) return res.status(401).end();
  next();
}
const requireRole = (role) => (req, res, next) => {
  if (req.user.role !== role) return res.status(403).end();
  next();
};
module.exports = { requireAuth, requireRole };
""",
    "server/user.js": """
const mongoose = require('mongoose');
const UserSchema = new mongoose.Schema({
  email: String,
  role: { type: String, enum: ['customer', 'manager', 'admin'], default: 'customer' },
});
module.exports = mongoose.model('User', UserSchema);
""",
    "server/order.js": """
const mongoose = require('mongoose');
const OrderSchema = new mongoose.Schema({
  user: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  address: String,
  status: { type: String, enum: ['new', 'shipped'], default: 'new' },
});
module.exports = mongoose.model('Order', OrderSchema);
""",
}

WEB = {
    "web/package.json": '{"dependencies": {"vue": "^3.4.0", "vue-router": "^4.3.0"}}',
    "web/src/router/index.js": """
import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue';

const routes = [
  { path: '/', component: HomeView },
  { path: '/register', component: () => import('../views/RegisterView.vue') },
  {
    path: '/app',
    component: () => import('../layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: 'orders', component: () => import('../views/OrdersView.vue') },
      {
        path: 'staff',
        component: () => import('../views/StaffOrdersView.vue'),
        meta: { roles: ['manager'] },
      },
    ],
  },
  {
    path: '/admin',
    component: () => import('../views/AdminView.vue'),
    meta: { requiresAdmin: true },
  },
  { path: '/:pathMatch(.*)*', component: () => import('../views/NotFound.vue') },
];

export default createRouter({ history: createWebHistory(), routes });
""",
    "web/src/views/HomeView.vue": "<template><h1>Bosh sahifa</h1></template>",
    "web/src/views/RegisterView.vue": """<template>
  <form @submit.prevent="register">
    <label for="email">{{ $t('auth.email') }}</label>
    <input id="email" v-model="form.email" type="email" required>
    <label>{{ $t('auth.password') }}
      <input v-model="form.password" type="password" minlength="8" required></label>
    <button type="submit">{{ $t('auth.signup') }}</button>
  </form>
</template>
<script setup>
import { reactive } from 'vue';
import axios from 'axios';
const form = reactive({ email: '', password: '' });
async function register() {
  await axios.post('/api/register', form);
}
</script>""",
    "web/src/layouts/AppLayout.vue": """<template>
  <nav><router-link to="/app/orders">{{ $t('nav.orders') }}</router-link></nav>
  <router-view />
</template>""",
    "web/src/views/OrdersView.vue": """<template>
  <ul><li v-for="o in orders" :key="o.id">{{ o.address }}</li></ul>
  <form @submit.prevent="create">
    <label for="address">Manzil</label>
    <input id="address" v-model="newOrder.address" required>
    <button type="submit">Buyurtma berish</button>
  </form>
</template>
<script>
import api from '../api';
export default {
  data() { return { orders: [], newOrder: { address: '' } }; },
  async created() { this.orders = (await api.get('/api/orders')).data; },
  methods: {
    async create() { await api.post('/api/orders', this.newOrder); },
  },
};
</script>""",
    "web/src/views/StaffOrdersView.vue": """<template>
  <div v-for="o in orders" :key="o.id">
    <button @click="ship(o.id)">Jo'natish</button>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue';
import api from '../api';
const orders = ref([]);
const load = async () => { orders.value = (await api.get('/api/staff/orders')).data; };
const ship = async (id) => { await api.post(`/api/staff/orders/${id}/ship`); };
onMounted(load);
</script>""",
    "web/src/views/AdminView.vue": "<template><h1>Admin</h1></template>",
    "web/src/views/NotFound.vue": "<template><h1>404</h1></template>",
    "web/src/locales/uz.json": (
        '{"auth": {"email": "Email", "password": "Parol", "signup": "Ro\'yxatdan o\'tish"},'
        ' "nav": {"orders": "Buyurtmalarim"}}'
    ),
}


def test_vue_router_meta_guards_and_components(tmp_path: Path, write_files: Writer) -> None:
    result = scan(write_files(tmp_path, {**API, **WEB}), "http://127.0.0.1:5173")
    bp = result.blueprint
    pages = {p.path: (p.access, p.roles) for p in bp.pages if p.kind == "page"}
    excluded = {p.path for p in bp.excluded}

    assert {"vue", "vue-router", "express"} <= set(result.stacks)
    assert pages["/"][0] == "guest" and pages["/register"][0] == "guest"
    assert pages["/app/orders"] == ("roles", ["customer", "manager"])
    assert pages["/app/staff"] == ("roles", ["manager"])  # parent auth + child roles
    assert "/admin" in excluded
    assert not any(":pathMatch" in p for p in pages)

    flows = {f.id: f for f in bp.flows}
    register = flows["customer.register"]
    labels = [s.target.label for s in register.steps if s.action == "fill" and s.target]
    assert labels == ["Email", "Parol"]
    create = flows["customer.order.create"]
    assert create.steps[0].path == "/app/orders"
    assert any(s.target and s.target.label == "Manzil" for s in create.steps)
    ship = flows["manager.order.ship"]
    assert ship.steps[-1].target is not None and ship.steps[-1].target.name == "Jo'natish"
    assert "customer.order.create" in ship.requires
    nav = {n["path"]: n["label"] for n in bp.nav}
    assert nav["/app/orders"] == "Buyurtmalarim"
