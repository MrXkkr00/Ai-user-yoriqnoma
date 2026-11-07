import uz from "./locales/uz.json";
import ru from "./locales/ru.json";

const dictionaries = { uz, ru };

export function getLang() {
  return localStorage.getItem("lang") || "uz";
}

export function setLang(lang) {
  localStorage.setItem("lang", lang);
}

// t("order.pay") -> "To'lash"
export function t(key) {
  const dict = dictionaries[getLang()] || uz;
  const value = key.split(".").reduce((node, part) => (node ? node[part] : undefined), dict);
  return value === undefined ? key : value;
}
