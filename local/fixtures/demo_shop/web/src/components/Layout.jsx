import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { t } from "../i18n.js";

export function NavBar() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  async function logout() {
    await api.post("/api/auth/logout");
    setUser(null);
    navigate("/");
  }

  return (
    <header className="navbar">
      <Link to="/" className="brand">
        {t("brand")}
      </Link>
      <nav>
        <NavLink to="/catalog">{t("nav.catalog")}</NavLink>
        {user && <NavLink to="/app/dashboard">{t("nav.dashboard")}</NavLink>}
        {user && user.role === "customer" && <NavLink to="/app/orders">{t("nav.orders")}</NavLink>}
        {user && user.role === "customer" && <NavLink to="/app/messages">{t("nav.messages")}</NavLink>}
        {user && user.role === "manager" && <NavLink to="/staff/orders">{t("nav.staffOrders")}</NavLink>}
        {user && user.role === "courier" && <NavLink to="/courier">{t("nav.courier")}</NavLink>}
        {user && user.role === "admin" && <NavLink to="/admin">{t("nav.admin")}</NavLink>}
        {user && <NavLink to="/app/profile">{t("nav.profile")}</NavLink>}
        {user && <NavLink to="/app/settings">{t("nav.settings")}</NavLink>}
      </nav>
      <div className="auth">
        {user ? (
          <button type="button" className="link" onClick={logout}>
            {t("nav.logout")}
          </button>
        ) : (
          <>
            <NavLink to="/login">{t("nav.login")}</NavLink>
            <NavLink to="/register" data-testid="nav-register">
              {t("nav.register")}
            </NavLink>
          </>
        )}
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <div>
        <strong>{t("footer.contacts")}</strong>
        <div>
          Email: <a href="mailto:info@demo-shop.uz">info@demo-shop.uz</a>
        </div>
        <div>
          Tel: <a href="tel:+998712000000">+998 71 200-00-00</a>
        </div>
        <div>{t("footer.address")}</div>
      </div>
      <div className="muted">© 2026 Demo Shop. {t("footer.rights")}</div>
    </footer>
  );
}

export default function Layout() {
  return (
    <div className="page">
      <NavBar />
      <main className="container">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
