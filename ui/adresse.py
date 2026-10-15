"""
Champ « Ta ville ou ton adresse » avec suggestions pendant la frappe.

Le navigateur interroge directement le service de suggestions de l'IGN (Géoplateforme, gratuit) :
les propositions s'affichent dès 3 lettres, sans recharger la page. Si le navigateur ne peut pas
joindre l'IGN, les suggestions passent par le serveur de l'application (un peu plus lentes).
Un clic sur une suggestion donne directement la position ; Entrée sans choisir lance la recherche
du texte tapé. L'adresse choisie est retenue sur l'appareil de l'élève seulement (navigateur), jamais
envoyée ailleurs que pour chercher les parcours.
"""

from __future__ import annotations

import streamlit as st

from core import decouverte

_HTML = """
<div class="addr">
  <label class="lbl"></label>
  <div class="box">
    <span class="ico" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    </span>
    <input type="text" autocomplete="off" spellcheck="false" role="combobox" aria-autocomplete="list"
           aria-expanded="false">
    <button type="button" class="clear" aria-label="Effacer" title="Effacer">×</button>
    <ul class="sugg" role="listbox"></ul>
  </div>
  <div class="hint"></div>
</div>
"""

_CSS = """
.addr { font-family: inherit; color: var(--st-text-color, #14233A); position: relative; }
.lbl { display: block; font-size: 14px; margin: 0 0 6px; }
.box { position: relative; display: flex; align-items: center; gap: 8px; background: var(--st-secondary-background-color, #F4F7FB);
       border: 1px solid var(--st-border-color, #D3DCE6); border-radius: 8px; padding: 0 8px 0 10px; height: 40px; }
.box:focus-within { border-color: var(--st-primary-color, #1B4F8C); box-shadow: 0 0 0 1px var(--st-primary-color, #1B4F8C); }
.ico { color: #7A8899; display: grid; place-items: center; }
input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit; font-size: 16px;
        color: inherit; height: 38px; }
.clear { border: 0; background: transparent; font-size: 22px; line-height: 1; color: #7A8899; cursor: pointer;
         padding: 0 4px; visibility: hidden; }
.clear.on { visibility: visible; }
.sugg { list-style: none; margin: 4px 0 0; padding: 4px; background: #fff; border: 1px solid #E3E9F0;
        border-radius: 10px; box-shadow: 0 10px 24px rgba(15,42,74,.18); display: none;
        position: absolute; left: 0; right: 0; top: 100%; z-index: 1000; }
.sugg.open { display: block; }
.sugg li { padding: 9px 10px; border-radius: 8px; cursor: pointer; display: flex; gap: 10px; align-items: baseline; }
.sugg li .k { font-size: 12px; color: #7A8899; flex: 0 0 auto; }
.sugg li.act, .sugg li:hover { background: #EEF3F8; }
.hint { font-size: 13px; color: #6B7A8C; margin-top: 4px; min-height: 0; }
.hint:empty { display: none; }
"""

_JS = """
export default function(component) {
  const { data, setStateValue, parentElement } = component;
  const root = parentElement.querySelector('.addr');
  if (!root) return;
  const input = root.querySelector('input');
  const list = root.querySelector('.sugg');
  const hint = root.querySelector('.hint');
  const clear = root.querySelector('.clear');
  const STORE = 'coach-running-adresse';
  root.__data = data || {};
  root.querySelector('.lbl').textContent = root.__data.label || 'Ta ville ou ton adresse';
  input.placeholder = root.__data.placeholder || '';

  const kindLabel = (k) => (k === 'adresse' ? 'adresse' : 'lieu');
  const show = (items) => {
    root.__items = items || [];
    root.__active = -1;
    list.innerHTML = '';
    root.__items.forEach((it, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      const t = document.createElement('span'); t.textContent = it.label;
      const k = document.createElement('span'); k.className = 'k'; k.textContent = kindLabel(it.kind);
      li.appendChild(t); li.appendChild(k);
      li.addEventListener('mousedown', (ev) => { ev.preventDefault(); choose(it); });
      list.appendChild(li);
    });
    const focused = (input.getRootNode && input.getRootNode().activeElement) || document.activeElement;
    const open = root.__items.length > 0 && focused === input;
    list.classList.toggle('open', open);
    input.setAttribute('aria-expanded', open ? 'true' : 'false');
  };
  const choose = (it) => {
    input.value = it.label;
    clear.classList.toggle('on', !!input.value);
    show([]);
    hint.textContent = '';
    try { localStorage.setItem(STORE, JSON.stringify(it)); } catch (e) {}
    setStateValue('place', { label: it.label, lat: it.lat, lon: it.lon, kind: it.kind || 'ville',
                             city: it.city || it.label });
  };
  const fromIgn = (r) => ({ label: r.fulltext, lat: r.y, lon: r.x, city: r.city || r.fulltext,
                            kind: (r.kind === 'housenumber' || r.kind === 'street') ? 'adresse' : 'ville' });

  // Suggestions venues du serveur (quand le navigateur ne joint pas l'IGN)
  if (root.__data.sugg_for && root.__data.sugg_for === input.value.trim()) {
    show(root.__data.sugg || []);
  }

  if (root.__ready) return;
  root.__ready = true;
  root.__server = false;
  let timer = null, seq = 0;

  const ask = (text) => {
    if (root.__server) { setStateValue('typed', text); return; }
    const mine = ++seq;
    const url = root.__data.url + '?text=' + encodeURIComponent(text) +
                '&type=StreetAddress,PositionOfInterest&maximumResponses=6';
    fetch(url).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((j) => { if (mine === seq && input.value.trim() === text)
                       show((j.results || []).filter((r) => r.fulltext).map(fromIgn)); })
      .catch(() => { root.__server = true; setStateValue('typed', text); });
  };

  input.addEventListener('input', () => {
    clear.classList.toggle('on', !!input.value);
    const text = input.value.trim();
    clearTimeout(timer);
    if (text.length < 3) { show([]); return; }
    timer = setTimeout(() => ask(text), 250);
  });
  input.addEventListener('keydown', (ev) => {
    const items = root.__items || [];
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      if (!items.length) return;
      ev.preventDefault();
      root.__active = (root.__active + (ev.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      [...list.children].forEach((li, i) => li.classList.toggle('act', i === root.__active));
    } else if (ev.key === 'Enter') {
      ev.preventDefault();
      if (root.__active >= 0 && items[root.__active]) { choose(items[root.__active]); return; }
      const text = input.value.trim();
      if (text) { show([]); setStateValue('place', { label: text, query: text }); }
    } else if (ev.key === 'Escape') { show([]); }
  });
  input.addEventListener('blur', () => setTimeout(() => show([]), 150));
  input.addEventListener('focus', () => { if ((root.__items || []).length) show(root.__items); });
  clear.addEventListener('click', () => {
    input.value = ''; clear.classList.remove('on'); show([]);
    try { localStorage.removeItem(STORE); } catch (e) {}
    setStateValue('place', null);
    input.focus();
  });

  // Valeur déjà choisie (rerun) ou adresse retenue sur cet appareil
  if (root.__data.value) {
    input.value = root.__data.value;
  } else if (root.__data.remember) {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE) || 'null');
      if (saved && saved.label && saved.lat !== undefined) {
        input.value = saved.label;
        hint.textContent = 'Adresse retenue sur cet appareil (× pour l\\'effacer)';
        setStateValue('place', saved);
      }
    } catch (e) {}
  }
  clear.classList.toggle('on', !!input.value);
}
"""

_component = st.components.v2.component("adresse_parcours", html=_HTML, css=_CSS, js=_JS)


@st.cache_data(ttl=24 * 3600, show_spinner=False, max_entries=500)
def _server_suggestions(text: str) -> list[dict]:
    try:
        return decouverte.complete(text)
    except decouverte.DiscoveryError:
        return []


def address_input(key: str, label: str = "Ta ville ou ton adresse",
                  placeholder: str = "ex. 12 rue Sainte-Catherine, Bordeaux ou Annecy",
                  remember: bool = True, on_change=None) -> dict | None:
    """Champ avec suggestions. Renvoie le lieu choisi : {label, lat, lon, kind} (suggestion) ou
    {label, query} (texte tapé puis Entrée), ou None."""
    state = st.session_state.get(key)
    current = (state or {}).get("place") if isinstance(state, dict) else getattr(state, "place", None)
    typed = (state or {}).get("typed") if isinstance(state, dict) else getattr(state, "typed", None)
    data = {"url": decouverte.IGN_COMPLETION_URL, "label": label, "placeholder": placeholder,
            "remember": remember, "value": (current or {}).get("label", "") if isinstance(current, dict) else ""}
    if typed:
        data.update(sugg=_server_suggestions(str(typed)), sugg_for=str(typed))
    result = _component(key=key, data=data, default={"place": None, "typed": None},
                        on_place_change=on_change or (lambda: None), on_typed_change=lambda: None)
    place = getattr(result, "place", None)
    return place if isinstance(place, dict) else None
