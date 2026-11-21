/* Кабинет ученика: общие помощники. window.S */
(function () {
  'use strict';
  var S = window.S = {};
  var MON = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  S.num = function (x) { var n = Number(x); return isFinite(n) ? n : 0; };
  S.rub = function (n) { return new Intl.NumberFormat('ru-RU').format(S.num(n)) + ' ₽'; };
  S.plural = function (n, a, b, c) { n = Math.abs(n) % 100; var k = n % 10; return n > 10 && n < 20 ? c : k > 1 && k < 5 ? b : k === 1 ? a : c; };
  S.date = function (iso) { var m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? (+m[3]) + ' ' + MON[+m[2] - 1] : ''; };
  S.stamp = function (x, f) { f = f || 'start'; return x && (x[f + '_at'] || x[f + '_time']) || ''; };
  S.dt = function (iso) { var d = S.date(iso), t = C.hhmm(iso); return (d ? d + (t ? ', ' : '') : '') + t; };
  S.safeUrl = function (u) { u = String(u || ''); return /^(https?:\/\/|\/)/i.test(u) && !/^\/\//.test(u) ? u : ''; };
  S.go = function (p) { return p.then(function (v) { return { v: v }; }, function (e) { if (e.status === 401) throw e; return { e: e }; }); };
  S.field = function (label, node) { var l = C.el('label', 'st-field'); l.appendChild(C.el('span', '', label)); l.appendChild(node); return l; };
  S.tabs = function (items, cur, onPick) {
    var w = C.el('div', 'st-tabs'); w.setAttribute('role', 'tablist');
    items.forEach(function (t) {
      var b = C.el('button', '', t[1]); b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(t[0] === cur));
      b.addEventListener('click', function () { onPick(t[0]); }); w.appendChild(b);
    });
    return w;
  };
  S.note = function (cls, text) { var d = C.el('p', 'st-note ' + (cls || ''), text); d.setAttribute('role', cls === 'bad' ? 'alert' : 'status'); return d; };
  S.b64 = function (file) { return new Promise(function (res, rej) { var r = new FileReader(); r.onload = function () { res(String(r.result).split(',')[1] || ''); }; r.onerror = rej; r.readAsDataURL(file); }); };
})();
