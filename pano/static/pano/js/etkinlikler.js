(function(){
  const rows = Array.from(document.querySelectorAll(".eventRowOne"));
  const img   = document.getElementById("posterImg");
  const empty = document.getElementById("posterEmpty");

  const ROTATE_MS = 5000;
  let idx = 0;

  function show(i){
    if (!rows.length) return;
    idx = (i + rows.length) % rows.length;

    rows.forEach(r => r.classList.remove("selected"));
    const row = rows[idx];
    row.classList.add("selected");
    row.scrollIntoView({ block: "nearest" });

    const poster = row.dataset.poster || "";
    if (poster){
      img.src = poster;
      img.style.display = "block";
      empty.style.display = "none";
    } else {
      img.removeAttribute("src");
      img.style.display = "none";
      empty.style.display = "flex";
      empty.textContent = "AFİŞ YOK";
    }
  }

  if (rows.length){
    show(0);
    setInterval(() => show(idx + 1), ROTATE_MS);
  } else {
    img.style.display = "none";
    empty.style.display = "flex";
    empty.textContent = "BU HAFTA ETKİNLİK YOK";
  }
})();

