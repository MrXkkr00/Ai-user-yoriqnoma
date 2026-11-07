import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { t } from "../i18n.js";

// Any logged-in user.
export function RequireAuth({ children }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <p>{t("common.loading")}</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

// Staff and customer pages: only users with this role.
export function RequireRole({ role, children }) {
  const { user, ready } = useAuth();
  if (!ready) return <p>{t("common.loading")}</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <p className="error">{t("common.forbidden")}</p>;
  return children;
}

// Admin area: users, roles and site settings.
export function RequireAdmin({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <p>{t("common.loading")}</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <p className="error">{t("common.forbidden")}</p>;
  return children;
}
