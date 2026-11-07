// Offline search over the manual. normalizeUz is the JS copy of
// yoriqnoma_core.text_uz.normalize_uz: "yuborish" finds «Yuboriş».
(function () {
  var NEW = { "ö": "o'", "ğ": "g'", "ş": "sh", "ç": "ch", "ı": "i", "ñ": "ng" };
  function normalizeUz(text) {
    var low = String(text || "").normalize("NFC").toLowerCase();
    var out = "";
    for (var i = 0; i < low.length; i++) { out += NEW[low[i]] !== undefined ? NEW[low[i]] : low[i]; }
    out = out.replace(/['‘’`ʻʼ´′]/g, "'");
    return out.replace(/\s+/g, " ").trim();
  }
  window.normalizeUz = normalizeUz;
  var input = document.getElementById("q");
  var list = document.getElementById("results");
  if (!input || !list) return;
  var index = (window.SEARCH_INDEX || []).map(function (e) {
    return { id: e.id, title: e.title, norm: normalizeUz(e.title + " " + e.text) };
  });
  input.addEventListener("input", function () {
    var q = normalizeUz(input.value);
    list.innerHTML = "";
    if (q.length < 2) { list.hidden = true; return; }
    var words = q.split(" ");
    var hits = index.filter(function (e) { return words.every(function (w) { return e.norm.indexOf(w) >= 0; }); });
    hits.slice(0, 12).forEach(function (e) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = "#" + e.id;
      a.textContent = e.title;
      li.appendChild(a);
      list.appendChild(li);
    });
    if (!hits.length) { var li = document.createElement("li"); li.textContent = "Hech narsa topilmadi"; list.appendChild(li); }
    list.hidden = false;
  });
})();
