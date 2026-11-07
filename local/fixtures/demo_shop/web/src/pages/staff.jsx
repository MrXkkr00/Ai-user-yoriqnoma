import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { t } from "../i18n.js";
import { StatusBadge } from "./cabinet.jsx";

function OrderTable({ orders, base }) {
  return (
    <table>
      <thead>
        <tr>
          <th>{t("order.number")}</th>
          <th>{t("order.customer")}</th>
          <th>{t("order.phone")}</th>
          <th>{t("order.product")}</th>
          <th>{t("order.status")}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {orders.map((o) => (
          <tr key={o.id}>
            <td>#{o.id}</td>
            <td>{o.customer_name}</td>
            <td>{o.phone}</td>
            <td>{o.product_name}</td>
            <td>
              <StatusBadge status={o.status} />
            </td>
            <td>
              <Link to={`${base}/${o.id}`}>{t("order.open")}</Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OrderCard({ order }) {
  return (
    <div className="card">
      <p>
        {t("order.customer")}: {order.customer_name}
      </p>
      <p>
        {t("order.phone")}: {order.phone}
      </p>
      <p>
        {t("order.address")}: {order.address}
      </p>
      <p>
        {t("order.product")}: {order.product_name} × {order.quantity}
      </p>
      {order.attachment_url && (
        <figure>
          <img src={order.attachment_url} alt={t("order.attachment")} width="480" />
          <figcaption>{t("order.attachment")}</figcaption>
        </figure>
      )}
    </div>
  );
}

export function StaffOrders() {
  const [orders, setOrders] = useState([]);
  useEffect(() => {
    api.get("/api/staff/orders").then(setOrders);
  }, []);
  return (
    <section>
      <h1>{t("staff.title")}</h1>
      <OrderTable orders={orders} base="/staff/orders" />
    </section>
  );
}

export function StaffOrder() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/api/staff/orders/${id}`).then(setOrder);
  }, [id]);

  async function shipOrder() {
    try {
      setOrder(await api.post(`/api/staff/orders/${id}/ship`));
    } catch (err) {
      setError(err.message);
    }
  }

  if (!order) return <p>{t("common.loading")}</p>;
  return (
    <section>
      <h1>
        {t("staff.detail")} #{order.id} <StatusBadge status={order.status} />
      </h1>
      <OrderCard order={order} />
      {error && <p className="error">{error}</p>}
      {order.status === "paid" && (
        <button type="button" onClick={shipOrder}>
          {t("order.ship")}
        </button>
      )}
    </section>
  );
}

export function CourierOrders() {
  const [orders, setOrders] = useState([]);
  useEffect(() => {
    api.get("/api/courier/orders").then(setOrders);
  }, []);
  return (
    <section>
      <h1>{t("courier.title")}</h1>
      {orders.length === 0 ? (
        <p className="muted">{t("courier.empty")}</p>
      ) : (
        <OrderTable orders={orders} base="/courier/orders" />
      )}
    </section>
  );
}

export function CourierOrder() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/api/courier/orders/${id}`).then(setOrder);
  }, [id]);

  async function deliverOrder() {
    try {
      setOrder(await api.post(`/api/courier/orders/${id}/deliver`));
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
      <OrderCard order={order} />
      {error && <p className="error">{error}</p>}
      {order.status === "shipped" && (
        <button type="button" onClick={deliverOrder}>
          {t("order.deliver")}
        </button>
      )}
    </section>
  );
}
