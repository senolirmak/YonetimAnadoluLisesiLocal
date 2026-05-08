(() => {
  'use strict';

  /* ======================================================
     CONFIG OKUMA
     Öncelik:
     1) window.PANO_CONFIG (base.html içinde üretilirse en iyisi)
     2) Template’ten gelen global JSON stringler (SCHOOL_NAME_JSON vs)
     3) Fallback default
  ====================================================== */

  const cfg = window.PANO_CONFIG || {};

  function safeJSONParse(v){
    if (v == null) return null;
    try {
      if (typeof v === "string") return JSON.parse(v);
      return v;
    } catch (e) {
      return null;
    }
  }

  const SCHOOL_NAME =
    cfg.SCHOOL_NAME ||
    safeJSONParse(window.SCHOOL_NAME_JSON) ||
    "Abdurrahim Karakoç Anadolu Lisesi";

  const LESSON_STARTS =
    (cfg.LESSON_STARTS && cfg.LESSON_STARTS.length) ? cfg.LESSON_STARTS :
    (safeJSONParse(window.DERSLER_JSON) || ["08:30","09:20","10:10","11:00","11:50","12:40","13:30","14:20"]);

  let ANNOUNCEMENTS =
    (cfg.ANNOUNCEMENTS && cfg.ANNOUNCEMENTS.length) ? cfg.ANNOUNCEMENTS :
    (safeJSONParse(window.DUYURULAR_JSON) || [
      "📢 Hoş geldiniz",
      "🔔 Dersler zamanında başlar",
      "🟥 Teneffüs süresi 10 dakikadır",
      "🏫 Okul saatlerine lütfen riayet ediniz",
      "📚 Telefonlar ders sırasında kapalı olmalıdır"
    ]);

  const LESSON_MIN = Number.isFinite(cfg.LESSON_MIN) ? cfg.LESSON_MIN : 40;
  const FLASH_MS = Number.isFinite(cfg.FLASH_MS) ? cfg.FLASH_MS : 900;
  const BLINK_ACTIVE_LESSON = (cfg.BLINK_ACTIVE_LESSON !== false);

  // Medya oynatma listesini al
  let MEDIA_PLAYLIST =
    (cfg.MEDIA_PLAYLIST && cfg.MEDIA_PLAYLIST.length) ? cfg.MEDIA_PLAYLIST : [];

  /* ======================================================
     RESPONSIVE SCALE + SCHOOL NAME FIT
  ====================================================== */
  function updateScale(){
    const w = window.innerWidth  || document.documentElement.clientWidth;
    const h = window.innerHeight || document.documentElement.clientHeight;
    const shortSide = Math.min(w, h);
    let s = shortSide / 1080;
    s = Math.max(0.75, Math.min(1.6, s));
    document.documentElement.style.setProperty("--scale", String(s));
    fitSchoolName();
  }

  function fitSchoolName(){
    const el = document.getElementById("schoolName");
    if (!el) return;

    el.style.setProperty("--schoolScale", 1);
    const maxW = el.clientWidth;
    const textW = el.scrollWidth;

    if (textW > maxW && maxW > 0){
      const scale = maxW / textW;
      el.style.setProperty("--schoolScale", Math.max(0.60, scale).toFixed(3));
    }
  }

  window.addEventListener("resize", updateScale);
  window.addEventListener("orientationchange", updateScale);

  /* ======================================================
     HEADER / TICKER (HER SAYFADA ÇALIŞSIN)
  ====================================================== */
  const schoolEl = document.getElementById("schoolName");
  if (schoolEl) schoolEl.textContent = SCHOOL_NAME;

  function updateTicker() {
    const tickerText = document.getElementById("tickerText");
    if (!tickerText) return;
    tickerText.textContent = ANNOUNCEMENTS.join("   |   ");
    // Animasyonu sıfırla — yeni metin hemen akışa girer
    const inner = tickerText.closest(".ticker-inner");
    if (inner) {
      inner.style.animation = "none";
      void inner.offsetWidth;
      inner.style.animation = "";
    }
  }
  updateTicker();

  // Kiosk iframe içindeyse sayfanın kendi ticker'ını gizle (kiosk üstte tutar)
  if (window.self !== window.top) {
    const ft = document.querySelector('.ticker');
    if (ft) ft.style.display = 'none';
  }

  updateScale();

  /* ======================================================
     ORTAK YARDIMCILAR
  ====================================================== */
  const daysTR = ["PAZAR","PAZARTESİ","SALI","ÇARŞAMBA","PERŞEMBE","CUMA","CUMARTESİ"];
  const pad = n => String(n).padStart(2,"0");

  function hhmmToMinutes(hhmm){
    const [h,m] = String(hhmm).split(":").map(Number);
    return h*60 + m;
  }
  function nowMinutes(d){
    return d.getHours()*60 + d.getMinutes() + d.getSeconds()/60;
  }
  function minToHHMM(mins){
    const h = Math.floor(mins / 60);
    const m = Math.floor(mins % 60);
    return `${pad(h)}:${pad(m)}`;
  }
  function fmtMMSS(totalSeconds){
    totalSeconds = Math.max(0, Math.floor(totalSeconds));
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${pad(m)}:${pad(s)}`;
  }

  /* ======================================================
     SAAT/DERS PANELİ (SADECE ELEMANLAR VARSA)
  ====================================================== */
  const timeEl = document.getElementById("time");
  const dateEl = document.getElementById("date");
  const dayEl  = document.getElementById("day");
  const dersList = document.getElementById("dersList");
  const flashEl = document.getElementById("flash");

  const counterTitle = document.getElementById("counterTitle");
  const counterValue = document.getElementById("counterValue");
  const counterSub   = document.getElementById("counterSub");

  /* ======================================================
     DERS LİSTESİ OLUŞTUR
  ====================================================== */
  const lineEls = [];
  function buildLessonList(){
    if (!dersList) return;
    dersList.innerHTML = "";
    lineEls.length = 0;

    LESSON_STARTS.forEach((hhmm, idx) => {
      const no = idx + 1;
      const line = document.createElement("div");
      line.className = "line";
      line.dataset.lesson = String(no);

      const lab = document.createElement("div");
      lab.className = "label";
      lab.textContent = `${no}. Ders`;

      const val = document.createElement("div");
      val.className = "val";
      val.textContent = hhmm;

      line.appendChild(lab);
      line.appendChild(val);
      dersList.appendChild(line);
      lineEls.push({ line });
    });
  }

  const startsMin = LESSON_STARTS.map(hhmmToMinutes);

  function getSchoolState(d){
    const t = nowMinutes(d);

    for (let i=0; i<startsMin.length; i++){
      const s = startsMin[i];
      const lessonEnd = s + LESSON_MIN;
      const nextStart = (i < startsMin.length-1) ? startsMin[i+1] : null;

      if (t >= s && t < lessonEnd){
        return { mode:"class", lesson:i+1, start:s, end:lessonEnd };
      }
      if (nextStart !== null && t >= lessonEnd && t < nextStart){
        return { mode:"break", lesson:i+1, start:lessonEnd, end:nextStart };
      }
    }
    return { mode:"off", lesson:null, start:null, end:null };
  }

  let lastLessonStartKey = null;

  function triggerFlash(){
    if (!flashEl) return;
    flashEl.classList.remove("on");
    void flashEl.offsetWidth;
    flashEl.classList.add("on");
    setTimeout(()=>flashEl.classList.remove("on"), FLASH_MS);
  }

  function clearLineStates(){
    for (const x of lineEls){
      x.line.classList.remove("active","blink","breakNow");
    }
  }

  function applyLineStates(state){
    clearLineStates();
    if (!state.lesson) return;

    const idx = state.lesson - 1;
    const el = lineEls[idx];
    if (!el) return;

    if (state.mode === "class"){
      el.line.classList.add("active");
      if (BLINK_ACTIVE_LESSON) el.line.classList.add("blink");
    } else if (state.mode === "break"){
      el.line.classList.add("breakNow","blink");
    }
  }

  function setBadge(state){
    const badge = document.getElementById("statusBadge");
    if (!badge) return;
    badge.classList.remove("class","break");
    if (state.mode === "class"){
      badge.classList.add("class");
      badge.textContent = `${state.lesson}. DERS`;
    } else if (state.mode === "break"){
      badge.classList.add("break");
      badge.textContent = "TENEFFÜS";
    } else {
      badge.textContent = "DERS DIŞI";
    }
  }

  function setCounters(state, d){
    if (state.mode === "class"){
      const remainingSec = (state.end - nowMinutes(d)) * 60;
      counterTitle.textContent = "DERSTE KALAN";
      counterValue.textContent = fmtMMSS(remainingSec);
      counterSub.textContent = `${state.lesson}. ders bitiş: ${minToHHMM(state.end)}`;
    } else if (state.mode === "break"){
      const remainingSec = (state.end - nowMinutes(d)) * 60;
      counterTitle.textContent = "TENEFFÜSTE KALAN";
      counterValue.textContent = fmtMMSS(remainingSec);
      counterSub.textContent = `Sonraki Ders: ${minToHHMM(state.end)}`;
    } else {
      counterTitle.textContent = "KALAN SÜRE";
      counterValue.textContent = "--:--";
      counterSub.textContent = "—";
    }
  }
  // Bağlantı durumunu kontrol et
  function checkConnection() {
      const errorEl = document.getElementById("connectionError");
      
      // Tarayıcının kendi offline kontrolü
      if (!navigator.onLine) {
          if (errorEl) errorEl.style.display = "block";
      } else {
          // Sunucuya küçük bir "ping" atalım (isteğe bağlı)
          fetch('/static/pano/img/logo.png', { method: 'HEAD', cache: 'no-store' })
              .then(() => {
                  if (errorEl) errorEl.style.display = "none";
              })
              .catch(() => {
                  if (errorEl) errorEl.style.display = "block";
              });
      }
  }

  // Her 30 saniyede bir kontrol et
  setInterval(checkConnection, 30000);
  /* ======================================================
     ANA DÖNGÜ
  ====================================================== */
  function tick(){
    const d = new Date();

    // Saat/tarih/gün elemanları varsa güncelle (kısmi sayfalarda da güncel kalsın)
    if (timeEl) timeEl.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    if (dateEl) dateEl.textContent = `${pad(d.getDate())}.${pad(d.getMonth()+1)}.${d.getFullYear()}`;
    if (dayEl)  dayEl.textContent  = daysTR[d.getDay()];

    const state = getSchoolState(d);
    setBadge(state);

    // 2. Okul İsmi (Varsa)
    const schoolEl = document.getElementById("schoolName");
    if (schoolEl) schoolEl.textContent = SCHOOL_NAME;

    if (dersList) applyLineStates(state);
    if (counterTitle && counterValue && counterSub) setCounters(state, d);

    // Ders başlangıcında flash
    if (state.mode === "class"){
      const startMin = Math.floor(state.start);
      const key = `${d.toDateString()}-${state.lesson}-${startMin}`;
      const minutesNowInt = d.getHours()*60 + d.getMinutes();
      if (minutesNowInt === startMin && d.getSeconds() <= 2 && lastLessonStartKey !== key){
        lastLessonStartKey = key;
        triggerFlash();
      }
    }
  }

  // Saat paneli varsa ders listesini kur
  buildLessonList();

  /* ======================================================
     MEDIA PLAYER (SAĞ PANEL) — A/B Çift Katman Crossfade
  ====================================================== */
  let _mediaIndex    = -1;
  let _mediaTimer    = null;
  let _mediaRunning  = false;
  let _activeLayer   = 'A';
  let _progressStart = null;
  let _progressDur   = 0;
  let _progressRaf   = null;

  function _layerEls(name) {
    return {
      layer: document.getElementById('mediaLayer' + name),
      img:   document.getElementById('mediaImage' + name),
      video: document.getElementById('mediaVideo' + name),
    };
  }

  function _switchLayer(nextName) {
    const cur = _layerEls(_activeLayer);
    const nxt = _layerEls(nextName);
    if (cur.layer) cur.layer.classList.remove('active');
    if (nxt.layer) nxt.layer.classList.add('active');
    _activeLayer = nextName;
  }

  function _startProgress(durationMs) {
    const bar = document.getElementById('mediaProgress');
    if (!bar) return;
    if (_progressRaf) cancelAnimationFrame(_progressRaf);
    _progressStart = performance.now();
    _progressDur   = durationMs;
    bar.style.width = '0%';
    function step(now) {
      const pct = Math.min(100, ((now - _progressStart) / _progressDur) * 100);
      bar.style.width = pct + '%';
      if (pct < 100) _progressRaf = requestAnimationFrame(step);
    }
    _progressRaf = requestAnimationFrame(step);
  }

  function _updateSlideCounter() {
    const el = document.getElementById('slideCounter');
    if (!el) return;
    el.textContent = MEDIA_PLAYLIST.length > 0
      ? `${_mediaIndex + 1} / ${MEDIA_PLAYLIST.length}`
      : '';
  }

  function _onPlaylistCycleDone() {
    if (window.parent !== window) {
      // Kiosk iframe içindeyiz — parent'a erken geçiş sinyali gönder
      window.parent.postMessage({ type: 'pano:mediaPlaylistDone' }, '*');
    } else {
      // Doğrudan açılmış — etkinlikler sayfasına git
      window.location.href = '/pano/etkinlikler/';
    }
  }

  function _playNext() {
    const emptyEl = document.getElementById('mediaEmpty');
    const titleEl = document.getElementById('mediaTitle');
    const descEl  = document.getElementById('mediaDesc');

    if (MEDIA_PLAYLIST.length === 0) {
      if (emptyEl) emptyEl.style.display = 'flex';
      return;
    }
    if (emptyEl) emptyEl.style.display = 'none';

    const nextIndex = (_mediaIndex + 1) % MEDIA_PLAYLIST.length;
    const cycleComplete = nextIndex < _mediaIndex; // sadece wrap-around'da true
    _mediaIndex = nextIndex;

    if (cycleComplete) {
      _onPlaylistCycleDone();
      return;
    }

    const item  = MEDIA_PLAYLIST[_mediaIndex];

    if (titleEl) titleEl.textContent = item.title       || '';
    if (descEl)  descEl.textContent  = item.description || '';
    _updateSlideCounter();

    const nextName = _activeLayer === 'A' ? 'B' : 'A';
    const nxt = _layerEls(nextName);

    if (item.type === 'image') {
      if (nxt.video) { nxt.video.pause(); nxt.video.removeAttribute('src'); nxt.video.style.display = 'none'; }
      nxt.img.src = item.url;
      nxt.img.style.display = 'block';
      _switchLayer(nextName);
      const dur = (item.duration || 15) * 1000;
      _startProgress(dur);
      _mediaTimer = setTimeout(_playNext, dur);
    } else if (item.type === 'video') {
      if (nxt.img) { nxt.img.removeAttribute('src'); nxt.img.style.display = 'none'; }
      nxt.video.src = item.url;
      nxt.video.currentTime = 0;
      nxt.video.style.display = 'block';
      _switchLayer(nextName);
      nxt.video.play().catch(e => console.error('Video oynatılamadı:', e));
    }
  }

  function setupMediaPlayer() {
    ['A', 'B'].forEach(name => {
      const v = document.getElementById('mediaVideo' + name);
      if (v) v.onended = () => { if (_mediaTimer) clearTimeout(_mediaTimer); _playNext(); };
    });
    _mediaRunning = true;
    _playNext();
  }

  function restartMediaPlayer() {
    if (_mediaTimer)    clearTimeout(_mediaTimer);
    if (_progressRaf)   cancelAnimationFrame(_progressRaf);
    _mediaIndex  = -1;
    _activeLayer = 'A';
    ['A', 'B'].forEach(name => {
      const els = _layerEls(name);
      if (els.video) { els.video.pause(); els.video.removeAttribute('src'); }
      if (els.img)   { els.img.removeAttribute('src'); }
      if (els.layer) { els.layer.classList.toggle('active', name === 'A'); }
    });
    _playNext();
  }

  /* ======================================================
     CONFIG POLLING — her 60 saniyede duyuru & medya güncelle
  ====================================================== */
  function pollConfig() {
    fetch('/pano/api/config/', { cache: 'no-store' })
      .then(r => r.json())
      .then(data => {
        const newAnn   = JSON.stringify(data.announcements   || []);
        const newMedia = JSON.stringify(data.media_playlist  || []);

        if (newAnn !== JSON.stringify(ANNOUNCEMENTS)) {
          ANNOUNCEMENTS = data.announcements || [];
          updateTicker();
        }

        if (newMedia !== JSON.stringify(MEDIA_PLAYLIST)) {
          MEDIA_PLAYLIST = data.media_playlist || [];
          if (_mediaRunning) restartMediaPlayer();
        }
      })
      .catch(() => {});
  }

  setInterval(pollConfig, 60_000);

  tick();
  setInterval(tick, 250);

  setupMediaPlayer();
})();