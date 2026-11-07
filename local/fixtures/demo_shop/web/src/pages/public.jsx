import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { t } from "../i18n.js";

export function Home() {
  return (
    <section className="hero">
      <h1>{t("home.title")}</h1>
      <p>{t("home.lead")}</p>
      <Link to="/catalog" className="button">
        {t("home.cta")}
      </Link>
    </section>
  );
}

export function Catalog() {
  const [products, setProducts] = useState([]);
  useEffect(() => {
    api.get("/api/products").then(setProducts);
  }, []);
  return (
    <section>
      <h1>{t("catalog.title")}</h1>
      <div className="grid">
        {products.map((p) => (
          <article key={p.id} className="card product">
            <h2>{p.name}</h2>
            <p>{p.description}</p>
            <p>
              {t("catalog.price")}: <b>{p.price.toLocaleString("ru-RU")} so'm</b>
            </p>
            <Link to={`/catalog/${p.id}`}>{t("catalog.details")}</Link>
          </article>
        ))}
      </div>
    </section>
  );
}

export function Product() {
  const { id } = useParams();
  const { user } = useAuth();
  const [product, setProduct] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [rating, setRating] = useState("5");
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/api/products/${id}`).then(setProduct);
    api.get(`/api/products/${id}/reviews`).then(setReviews);
  }, [id]);

  async function submitReview(event) {
    event.preventDefault();
    setError("");
    try {
      const review = await api.post(`/api/products/${id}/reviews`, { rating: Number(rating), text });
      setReviews([...reviews, review]);
      setText("");
    } catch (err) {
      setError(err.message);
    }
  }

  if (!product) return <p>{t("common.loading")}</p>;
  return (
    <section>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <p>
        {t("catalog.price")}: <b>{product.price.toLocaleString("ru-RU")} so'm</b>
      </p>
      {user && user.role === "customer" && (
        <Link to={`/app/orders/new?product=${product.id}`} className="button">
          {t("catalog.order")}
        </Link>
      )}

      <h2>{t("catalog.reviews")}</h2>
      {reviews.length === 0 && <p className="muted">{t("catalog.noReviews")}</p>}
      <div className="reviews">
        {reviews.map((r) => (
          <div key={r.id} className="review" itemScope itemType="https://schema.org/Review">
            <div className="review-head">
              <span className="avatar" aria-hidden="true">
                {r.author_name.slice(0, 1)}
              </span>
              <span itemProp="author">{r.author_name}</span>
              <span className="stars">{"★".repeat(r.rating)}</span>
            </div>
            <p itemProp="reviewBody">{r.text}</p>
          </div>
        ))}
      </div>

      {user && user.role === "customer" ? (
        <form onSubmit={submitReview} className="card">
          <h3>{t("catalog.writeReview")}</h3>
          <label htmlFor="rating">{t("catalog.rating")}</label>
          <select id="rating" name="rating" value={rating} onChange={(e) => setRating(e.target.value)}>
            {["5", "4", "3", "2", "1"].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <label htmlFor="review-text">{t("catalog.reviewText")}</label>
          <textarea
            id="review-text"
            name="text"
            required
            minLength={3}
            maxLength={1000}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {error && <p className="error">{error}</p>}
          <button type="submit">{t("catalog.sendReview")}</button>
        </form>
      ) : (
        <p className="muted">{t("catalog.loginToReview")}</p>
      )}
    </section>
  );
}

export function NotFound() {
  return <p>404</p>;
}
