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

const EMPTY_USER = { full_name: "", email: "", phone: "", password: "", role: "customer" };

export function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY_USER);
  const [error, setError] = useState("");
  const load = () => api.get("/api/admin/users").then(setUsers);
  useEffect(() => {
    load();
  }, []);

  function change(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/admin/users", form);
      setForm(EMPTY_USER);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(user) {
    if (!window.confirm(`${user.email}: ${t("admin.confirmDelete")}`)) return;
    try {
      await api.del(`/api/admin/users/${user.id}`);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <h1>{t("admin.users")}</h1>
      <form className="card" onSubmit={create}>
        <h2>{t("admin.newUser")}</h2>
        <label htmlFor="new-full_name">{t("auth.fullName")}</label>
        <input id="new-full_name" name="full_name" required minLength={3} value={form.full_name} onChange={change} />
        <label htmlFor="new-email">{t("auth.email")}</label>
        <input id="new-email" name="email" type="email" required value={form.email} onChange={change} />
        <label htmlFor="new-phone">{t("auth.phone")}</label>
        <input id="new-phone" name="phone" type="tel" required pattern="^\+998\d{9}$" value={form.phone} onChange={change} />
        <label htmlFor="new-password">{t("auth.password")}</label>
        <input id="new-password" name="password" type="password" required minLength={8} value={form.password} onChange={change} />
        <label htmlFor="new-role">{t("admin.role")}</label>
        <select id="new-role" name="role" value={form.role} onChange={change}>
          <option value="customer">customer</option>
          <option value="manager">manager</option>
          <option value="courier">courier</option>
        </select>
        {error && <p className="error">{error}</p>}
        <button type="submit">{t("admin.create")}</button>
      </form>
      <table>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>{u.full_name}</td>
              <td>{u.role}</td>
              <td>
                {u.role !== "admin" && (
                  <button type="button" onClick={() => remove(u)}>
                    {t("admin.delete")}
                  </button>
                )}
              </td>
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
