import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { t } from "../i18n.js";

export function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "" });
  const [error, setError] = useState("");

  function change(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/auth/register", form);
      navigate(`/verify-email?email=${encodeURIComponent(form.email)}`);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>{t("auth.registerTitle")}</h1>
      <label htmlFor="full_name">{t("auth.fullName")}</label>
      <input id="full_name" name="full_name" required minLength={3} maxLength={80} value={form.full_name} onChange={change} />
      <label htmlFor="email">{t("auth.email")}</label>
      <input id="email" name="email" type="email" required value={form.email} onChange={change} />
      <label htmlFor="phone">{t("auth.phone")}</label>
      <input
        id="phone"
        name="phone"
        type="tel"
        required
        pattern="^\+998\d{9}$"
        placeholder="+998901234567"
        value={form.phone}
        onChange={change}
      />
      <label htmlFor="password">{t("auth.password")}</label>
      <input id="password" name="password" type="password" required minLength={8} maxLength={64} value={form.password} onChange={change} />
      {error && <p className="error">{error}</p>}
      <button type="submit" data-testid="register-submit">
        {t("auth.submitRegister")}
      </button>
      <p className="muted">
        {t("auth.haveAccount")} <Link to="/login">{t("nav.login")}</Link>
      </p>
    </form>
  );
}

export function VerifyEmail() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState(params.get("email") || "");
  const [code, setCode] = useState(params.get("code") || "");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/auth/verify-email", { email, code });
      setDone(true);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>{t("auth.verifyTitle")}</h1>
      <p>{t("auth.verifyLead")}</p>
      <label htmlFor="verify-email">{t("auth.email")}</label>
      <input id="verify-email" name="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="code">{t("auth.code")}</label>
      <input
        id="code"
        name="code"
        required
        pattern="^\d{6}$"
        inputMode="numeric"
        value={code}
        onChange={(e) => setCode(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      {done ? (
        <p className="ok">
          {t("auth.verified")} <Link to="/login">{t("nav.login")}</Link>
        </p>
      ) : (
        <button type="submit">{t("auth.submitVerify")}</button>
      )}
    </form>
  );
}

export function Login() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const user = await api.post("/api/auth/login", { email, password });
      setUser(user);
      navigate("/app/dashboard");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>{t("auth.loginTitle")}</h1>
      <label htmlFor="login-email">{t("auth.email")}</label>
      <input id="login-email" name="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="login-password">{t("auth.password")}</label>
      <input
        id="login-password"
        name="password"
        type="password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {error && <p className="error">{error}</p>}
      <button type="submit">{t("auth.submitLogin")}</button>
      <p className="muted">
        <Link to="/forgot-password">{t("auth.forgot")}</Link>
        {" · "}
        {t("auth.noAccount")} <Link to="/register">{t("nav.register")}</Link>
      </p>
    </form>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  async function submit(event) {
    event.preventDefault();
    await api.post("/api/auth/forgot-password", { email });
    setSent(true);
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h1>{t("auth.forgotTitle")}</h1>
      <p>{t("auth.forgotLead")}</p>
      <label htmlFor="forgot-email">{t("auth.email")}</label>
      <input id="forgot-email" name="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      {sent ? <p className="ok">{t("auth.forgotSent")}</p> : <button type="submit">{t("auth.submitForgot")}</button>}
    </form>
  );
}
