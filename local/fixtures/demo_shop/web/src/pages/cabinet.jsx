import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { setLang, t } from "../i18n.js";
import Modal from "../components/Modal.jsx";

export function StatusBadge({ status }) {
  return <span className={`badge status-${status}`}>{t(`status.${status}`)}</span>;
}

export function Dashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  useEffect(() => {
    if (user.role === "customer") api.get("/api/orders").then(setOrders);
  }, [user]);
  return (
    <section>
      <h1>{t("dashboard.title")}</h1>
      <p>
        {t("dashboard.hello")}, <b>{user.full_name}</b>!
      </p>
      <p>
        {t("dashboard.role")}: {user.role}
      </p>
      {user.role === "customer" && (
        <div className="card">
          {t("dashboard.ordersCount")}: <b>{orders.length}</b>{" "}
          <Link to="/app/orders">{t("nav.orders")}</Link>
        </div>
      )}
    </section>
  );
}

export function Orders() {
  const [orders, setOrders] = useState(null);
  useEffect(() => {
    api.get("/api/orders").then(setOrders);
  }, []);
  if (!orders) return <p>{t("common.loading")}</p>;
  return (
    <section>
      <div className="row">
        <h1>{t("order.listTitle")}</h1>
        <Link to="/app/orders/new" className="button" data-testid="new-order">
          {t("order.new")}
        </Link>
      </div>
      {orders.length === 0 ? (
        <p className="muted">{t("order.empty")}</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{t("order.number")}</th>
              <th>{t("order.product")}</th>
              <th>{t("order.total")}</th>
              <th>{t("order.status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>#{o.id}</td>
                <td>{o.product_name}</td>
                <td>{o.total.toLocaleString("ru-RU")} so'm</td>
                <td>
                  <StatusBadge status={o.status} />
                </td>
                <td>
                  <Link to={`/app/orders/${o.id}`}>{t("order.open")}</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function OrderNew() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState({
    product_id: params.get("product") || "1",
    quantity: "1",
    address: "",
    phone: "",
  });
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/products").then(setProducts);
  }, []);

  function change(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function createOrder(event) {
    event.preventDefault();
    setError("");
    try {
      const order = await api.post("/api/orders", {
        product_id: Number(form.product_id),
        quantity: Number(form.quantity),
        address: form.address,
        phone: form.phone,
      });
      navigate(`/app/orders/${order.id}`);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card narrow" onSubmit={createOrder}>
      <h1>{t("order.new")}</h1>
      <label htmlFor="product_id">{t("order.product")}</label>
      <select id="product_id" name="product_id" value={form.product_id} onChange={change}>
        {products.map((p) => (
          <option key={p.id} value={String(p.id)}>
            {p.name}
          </option>
        ))}
      </select>
      <label htmlFor="quantity">{t("order.quantity")}</label>
      <input id="quantity" name="quantity" type="number" required min={1} max={99} value={form.quantity} onChange={change} />
      <label htmlFor="address">{t("order.address")}</label>
      <input id="address" name="address" required minLength={5} maxLength={200} value={form.address} onChange={change} />
      <label htmlFor="order-phone">{t("order.phone")}</label>
      <input
        id="order-phone"
        name="phone"
        type="tel"
        required
        pattern="^\+998\d{9}$"
        placeholder="+998901234567"
        value={form.phone}
        onChange={change}
      />
      {error && <p className="error">{error}</p>}
      <button type="submit">{t("order.submitNew")}</button>
    </form>
  );
}

export function OrderDetail() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState("details");
  const [modal, setModal] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setOrder(await api.get(`/api/orders/${id}`));
    setHistory(await api.get(`/api/orders/${id}/history`));
  }

  useEffect(() => {
    load();
  }, [id]);

  async function payOrder() {
    try {
      setOrder(await api.post(`/api/orders/${id}/pay`));
      setModal("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function cancelOrder() {
    try {
      setOrder(await api.post(`/api/orders/${id}/cancel`));
      setModal("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!order) return <p>{t("common.loading")}</p>;
  return (
    <section>
      <h1>
        {t("order.number")} #{order.id} <StatusBadge status={order.status} />
      </h1>
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "details"} onClick={() => setTab("details")}>
          {t("order.tabDetails")}
        </button>
        <button type="button" role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>
          {t("order.tabHistory")}
        </button>
      </div>

      {tab === "details" ? (
        <div className="card" role="tabpanel">
          <p>
            {t("order.product")}: {order.product_name} × {order.quantity}
          </p>
          <p>
            {t("order.total")}: {order.total.toLocaleString("ru-RU")} so'm
          </p>
          <p>
            {t("order.address")}: {order.address}
          </p>
          <p>
            {t("order.phone")}: {order.phone}
          </p>
          <div className="actions">
            {order.status === "new" && (
              <button type="button" onClick={() => setModal("pay")}>
                {t("order.pay")}
              </button>
            )}
            {order.status === "new" && (
              <button type="button" className="danger" onClick={() => setModal("cancel")}>
                {t("order.cancel")}
              </button>
            )}
            <a href={`/api/orders/${order.id}/invoice`} download className="button secondary">
              {t("order.invoice")}
            </a>
          </div>
        </div>
      ) : (
        <ol className="card" role="tabpanel">
          {history.map((h, i) => (
            <li key={i}>
              <StatusBadge status={h.status} /> {new Date(h.at).toLocaleString("ru-RU")}
            </li>
          ))}
        </ol>
      )}
      {error && <p className="error">{error}</p>}

      {modal === "pay" && (
        <Modal title={t("order.payTitle")} onClose={() => setModal("")}>
          <p>{t("order.payLead")}</p>
          <button type="button" onClick={payOrder}>
            {t("order.payConfirm")}
          </button>
        </Modal>
      )}
      {modal === "cancel" && (
        <Modal title={t("order.cancelTitle")} onClose={() => setModal("")}>
          <p>{t("order.cancelLead")}</p>
          <button type="button" className="danger" onClick={cancelOrder}>
            {t("order.cancelConfirm")}
          </button>
        </Modal>
      )}
    </section>
  );
}

export function Messages() {
  const [messages, setMessages] = useState([]);
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setMessages(await api.get("/api/messages"));
  }

  useEffect(() => {
    load();
  }, []);

  async function sendMessage(event) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/messages", { to_email: to, text });
      setText("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <h1>{t("messages.title")}</h1>
      {messages.length === 0 && <p className="muted">{t("messages.empty")}</p>}
      <ul className="messages">
        {messages.map((m) => (
          <li key={m.id} className={m.outgoing ? "out" : "in"}>
            <b>{m.outgoing ? t("messages.you") : m.other_name}</b>: {m.text}
          </li>
        ))}
      </ul>
      <form className="card" onSubmit={sendMessage}>
        <label htmlFor="to_email">{t("messages.to")}</label>
        <input id="to_email" name="to_email" type="email" required value={to} onChange={(e) => setTo(e.target.value)} />
        <label htmlFor="message-text">{t("messages.text")}</label>
        <textarea id="message-text" name="text" required maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
        {error && <p className="error">{error}</p>}
        <button type="submit">{t("messages.send")}</button>
      </form>
    </section>
  );
}

export function Profile() {
  const { user, refresh } = useAuth();
  const [form, setForm] = useState({ full_name: user.full_name, phone: user.phone });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function change(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function saveProfile(event) {
    event.preventDefault();
    setError("");
    try {
      await api.put("/api/profile", form);
      setSaved(true);
      refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card narrow" onSubmit={saveProfile}>
      <h1>{t("profile.title")}</h1>
      <p className="muted">{user.email}</p>
      <label htmlFor="profile-name">{t("auth.fullName")}</label>
      <input id="profile-name" name="full_name" required minLength={3} maxLength={80} value={form.full_name} onChange={change} />
      <label htmlFor="profile-phone">{t("auth.phone")}</label>
      <input id="profile-phone" name="phone" type="tel" required pattern="^\+998\d{9}$" value={form.phone} onChange={change} />
      {error && <p className="error">{error}</p>}
      {saved && <p className="ok">{t("profile.saved")}</p>}
      <button type="submit">{t("profile.save")}</button>
    </form>
  );
}

export function Settings() {
  const { user } = useAuth();
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [notify, setNotify] = useState(user.notify_email);
  const [language, setLanguage] = useState(user.language || "uz");
  const [message, setMessage] = useState("");

  async function changePassword(event) {
    event.preventDefault();
    try {
      await api.put("/api/settings/password", passwords);
      setMessage(t("settings.saved"));
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function saveNotifications(event) {
    event.preventDefault();
    await api.put("/api/settings/notifications", { notify_email: notify });
    setMessage(t("settings.saved"));
  }

  async function saveLanguage(event) {
    event.preventDefault();
    await api.put("/api/settings/language", { language });
    setLang(language);
    setMessage(t("settings.saved"));
  }

  return (
    <section>
      <h1>{t("settings.title")}</h1>
      {message && <p className="ok">{message}</p>}
      <form className="card" onSubmit={changePassword}>
        <h2>{t("settings.passwordTitle")}</h2>
        <label htmlFor="current_password">{t("settings.currentPassword")}</label>
        <input
          id="current_password"
          name="current_password"
          type="password"
          required
          value={passwords.current_password}
          onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })}
        />
        <label htmlFor="new_password">{t("settings.newPassword")}</label>
        <input
          id="new_password"
          name="new_password"
          type="password"
          required
          minLength={8}
          value={passwords.new_password}
          onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })}
        />
        <button type="submit">{t("settings.changePassword")}</button>
      </form>
      <form className="card" onSubmit={saveNotifications}>
        <h2>{t("settings.notifyTitle")}</h2>
        <label className="check">
          <input type="checkbox" name="notify_email" checked={notify} onChange={(e) => setNotify(e.target.checked)} />{" "}
          {t("settings.notifyEmail")}
        </label>
        <button type="submit">{t("settings.saveNotify")}</button>
      </form>
      <form className="card" onSubmit={saveLanguage}>
        <h2>{t("settings.languageTitle")}</h2>
        <label htmlFor="language">{t("settings.language")}</label>
        <select id="language" name="language" value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="uz">O'zbekcha</option>
          <option value="ru">Русский</option>
        </select>
        <button type="submit">{t("settings.saveLanguage")}</button>
      </form>
      {user.role === "customer" && (
        <p>
          <Link to="/app/account/delete" className="danger-link">
            {t("settings.deleteLink")}
          </Link>
        </p>
      )}
    </section>
  );
}

export function AccountDelete() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function deleteAccount(event) {
    event.preventDefault();
    try {
      await api.post("/api/account/delete", { password });
      setUser(null);
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card narrow" onSubmit={deleteAccount}>
      <h1>{t("delete.title")}</h1>
      <p>{t("delete.lead")}</p>
      <label htmlFor="delete-password">{t("delete.password")}</label>
      <input id="delete-password" name="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="error">{error}</p>}
      <button type="submit" className="danger">
        {t("delete.submit")}
      </button>
    </form>
  );
}
