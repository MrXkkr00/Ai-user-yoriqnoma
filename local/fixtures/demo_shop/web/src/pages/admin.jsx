import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { t } from "../i18n.js";

export function AdminHome() {
  return (
    <section>
      <h1>{t("admin.title")}</h1>
      <ul>
        <li>
          <Link to="/admin/users">{t("admin.users")}</Link>
        </li>
        <li>
          <Link to="/admin/roles">{t("admin.roles")}</Link>
        </li>
      </ul>
    </section>
  );
}

export function AdminUsers() {
  const [users, setUsers] = useState([]);
  useEffect(() => {
    api.get("/api/admin/users").then(setUsers);
  }, []);
  return (
    <section>
      <h1>{t("admin.users")}</h1>
      <table>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>{u.full_name}</td>
              <td>{u.role}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function AdminRoles() {
  const [roles, setRoles] = useState([]);
  useEffect(() => {
    api.get("/api/admin/roles").then(setRoles);
  }, []);
  return (
    <section>
      <h1>{t("admin.roles")}</h1>
      <ul>
        {roles.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
    </section>
  );
}

export function AdminRefund() {
  const { id } = useParams();
  const [done, setDone] = useState(false);

  async function refundOrder() {
    await api.post(`/api/admin/orders/${id}/refund`);
    setDone(true);
  }

  return (
    <section>
      <h1>{t("admin.refund")}</h1>
      {done ? <p>OK</p> : <button onClick={refundOrder}>{t("admin.refund")}</button>}
    </section>
  );
}
