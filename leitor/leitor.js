/* Leitor de documentos do ICET (mesmo leitor do livro da Editora).
   Uso: um elemento .livro3d com data-doc="caminho/da/pasta/" abre o leitor;
   a pasta contém livro.json, texto.json, p/NNN.webp e t/NNN.webp. */
(function(){
'use strict';
var $ = function(s, c){ return (c || document).querySelector(s); };
var $$ = function(s, c){ return Array.prototype.slice.call((c || document).querySelectorAll(s)); };
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function pad(n){ n = String(n); while(n.length < 3) n = '0' + n; return n; }
var L = {
  pt:{pagina:'Página',sum:'Sumário',bus:'Buscar',busca_t:'Buscar no documento',ouvir:'Ouvir',lendo:'Lendo em voz alta',parar:'Parar',sem:'Nada encontrado.',res:'resultados',carregando:'Carregando o texto…',ph:'Digite uma palavra',baixar:'Baixar PDF',semsum:'Use as miniaturas para navegar pelas páginas.'},
  en:{pagina:'Page',sum:'Contents',bus:'Search',busca_t:'Search the document',ouvir:'Listen',lendo:'Reading aloud',parar:'Stop',sem:'Nothing found.',res:'results',carregando:'Loading text…',ph:'Type a word',baixar:'Download PDF',semsum:'Use the thumbnails to browse the pages.'},
  es:{pagina:'Página',sum:'Índice',bus:'Buscar',busca_t:'Buscar en el documento',ouvir:'Escuchar',lendo:'Leyendo en voz alta',parar:'Detener',sem:'Sin resultados.',res:'resultados',carregando:'Cargando el texto…',ph:'Escribe una palabra',baixar:'Descargar PDF',semsum:'Usa las miniaturas para recorrer las páginas.'},
  fr:{pagina:'Page',sum:'Sommaire',bus:'Rechercher',busca_t:'Rechercher dans le document',ouvir:'Écouter',lendo:'Lecture à voix haute',parar:'Arrêter',sem:'Aucun résultat.',res:'résultats',carregando:'Chargement du texte…',ph:'Tapez un mot',baixar:'Télécharger le PDF',semsum:'Utilisez les miniatures pour parcourir les pages.'}
};
function lg(){ var l = null; try{ ['icet_lang','focams_lang','cmddi_lang'].some(function(k){ l = localStorage.getItem(k); return !!l; }); }catch(e){} l = (l || document.documentElement.lang || 'pt').slice(0, 2); return L[l] ? l : 'pt'; }
function t(k){ return L[lg()][k] || L.pt[k]; }
var IC = {
  x:'<path d="M18 6 6 18M6 6l12 12"/>', sum:'<path d="M4 6h16M4 12h16M4 18h10"/>', bus:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  ouv:'<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/>', mini:'<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="9"/><rect x="3" y="15" width="7" height="6"/><rect x="14" y="15" width="7" height="6"/>',
  zoom:'<circle cx="11" cy="11" r="7"/><path d="M11 8v6M8 11h6M20 20l-3.5-3.5"/>', tela:'<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  esq:'<path d="m15 18-6-6 6-6"/>', dir:'<path d="m9 18 6-6-6-6"/>'
};
function svg(k, w){ return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + (w || 2) + '">' + IC[k] + '</svg>'; }
var ld, esp, DOC = null, TEXTO = null, atual = 1, duplo = false, animando = false, falando = false;
function montarUI(){
  if(ld) return;
  ld = document.createElement('div'); ld.className = 'ldoc'; ld.setAttribute('role', 'dialog'); ld.setAttribute('aria-modal', 'true');
  ld.innerHTML = '<div class="lt-barra"><button class="lt-bt" data-a="fechar" aria-label="Fechar">' + svg('x') + '</button><div class="tt"></div>' +
    '<div class="lt-pg"><label for="ldoc-ir">Página</label><input id="ldoc-ir" type="number" min="1" inputmode="numeric"><span class="tot"></span></div>' +
    '<button class="lt-bt" data-a="sum">' + svg('sum') + '<span class="rotulo" data-l="sum"></span></button>' +
    '<button class="lt-bt" data-a="bus">' + svg('bus') + '<span class="rotulo" data-l="bus"></span></button>' +
    '<button class="lt-bt" data-a="ouvir">' + svg('ouv') + '<span class="rotulo" data-l="ouvir"></span></button>' +
    '<button class="lt-bt" data-a="mini" aria-label="Miniaturas">' + svg('mini') + '</button>' +
    '<button class="lt-bt" data-a="zoom" aria-label="Ampliar">' + svg('zoom') + '</button>' +
    '<button class="lt-bt" data-a="tela" aria-label="Tela cheia">' + svg('tela') + '</button>' +
    '<a class="lt-baixar" target="_blank" rel="noopener" data-l="baixar"></a></div>' +
    '<div class="lt-prog"><i></i></div><div class="lt-corpo"><div class="espelho"></div>' +
    '<button class="lt-seta ant" aria-label="Anterior">' + svg('esq', 2.4) + '</button><button class="lt-seta prox" aria-label="Próxima">' + svg('dir', 2.4) + '</button>' +
    '<div class="lt-ouvindo"><div class="onda"><i></i><i></i><i></i><i></i></div><span data-l="lendo"></span><button class="lt-bt" data-a="parar" data-l="parar"></button></div>' +
    '<div class="lt-painel"><h4></h4><div class="ps"><input type="search"></div><div class="lt-res"></div></div>' +
    '<div class="lt-zoom"><img alt=""></div></div><div class="lt-miniaturas"></div>';
  document.body.appendChild(ld); esp = $('.espelho', ld);
  var A = function(a){ return $('[data-a="' + a + '"]', ld); };
  A('fechar').addEventListener('click', fechar);
  $('.lt-seta.ant', ld).addEventListener('click', function(){ ir(atual - passo(), true); });
  $('.lt-seta.prox', ld).addEventListener('click', function(){ ir(atual + passo(), true); });
  $('#ldoc-ir').addEventListener('change', function(){ ir(+this.value); });
  A('mini').addEventListener('click', function(){ this.classList.toggle('on'); $('.lt-miniaturas', ld).classList.toggle('on'); render(); });
  A('zoom').addEventListener('click', function(){ ampliar(atual); });
  A('tela').addEventListener('click', function(){ try{ if(document.fullscreenElement) document.exitFullscreen(); else ld.requestFullscreen(); }catch(e){} });
  A('sum').addEventListener('click', painelSum); A('bus').addEventListener('click', painelBus);
  A('ouvir').addEventListener('click', ouvir); A('parar').addEventListener('click', pararFala);
  $('.lt-zoom', ld).addEventListener('click', function(){ this.classList.remove('on'); });
  esp.addEventListener('dblclick', function(e){ var im = e.target.closest('img[data-n]'); if(im) ampliar(+im.getAttribute('data-n')); });
  var tb = null; $('.lt-painel input', ld).addEventListener('input', function(){ var q = this.value; clearTimeout(tb); tb = setTimeout(function(){ buscar(q); }, 220); });
  addEventListener('keydown', function(e){
    if(!ld.classList.contains('aberto') || e.target.tagName === 'INPUT') return;
    if(e.key === 'ArrowRight' || e.key === 'PageDown'){ ir(atual + passo(), true); e.preventDefault(); }
    else if(e.key === 'ArrowLeft' || e.key === 'PageUp'){ ir(atual - passo(), true); e.preventDefault(); }
    else if(e.key === 'Home') ir(1); else if(e.key === 'End') ir(DOC.paginas);
    else if(e.key === 'Escape'){ var z = $('.lt-zoom', ld), p = $('.lt-painel', ld); if(z.classList.contains('on')) z.classList.remove('on'); else if(p.classList.contains('on')) p.classList.remove('on'); else fechar(); }
  });
  addEventListener('resize', function(){ if(ld.classList.contains('aberto')) render(); });
  var x0 = null, y0 = null, c = $('.lt-corpo', ld);
  c.addEventListener('touchstart', function(e){ if(e.touches.length === 1){ x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; } }, { passive: true });
  c.addEventListener('touchend', function(e){ if(x0 == null) return; var dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0; if(Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.4) ir(atual + (dx < 0 ? passo() : -passo()), true); x0 = null; });
}
function rotular(){ $$('[data-l]', ld).forEach(function(e){ e.textContent = t(e.getAttribute('data-l')); }); $('.lt-painel input', ld).placeholder = t('ph'); }
function src(n, mini){ return DOC.base + (mini ? 't/' : 'p/') + pad(n) + '.webp'; }
function ehDuplo(){ return DOC.prop < 1 && innerWidth > 980 && innerWidth / innerHeight > 1.15; }
function par(n){ if(!duplo) return [n]; if(n === 1) return [null, 1]; var e = n % 2 === 0 ? n : n - 1; return [e, e + 1 <= DOC.paginas ? e + 1 : null]; }
function folha(n, lado){ if(!n) return '<div class="folha ' + lado + ' vazia"></div>'; return '<div class="folha ' + lado + '"><img src="' + src(n) + '" alt="' + t('pagina') + ' ' + n + '" draggable="false" data-n="' + n + '"></div>'; }
function medir(){ var c = $('.lt-corpo', ld), W = c.clientWidth - (innerWidth > 760 ? 140 : 24), H = c.clientHeight - 28; var fw = Math.min(H * DOC.prop, duplo ? W / 2 : W); esp.style.setProperty('--fw', Math.floor(fw) + 'px'); esp.style.setProperty('--fh', Math.floor(fw / DOC.prop) + 'px'); }
function render(){
  duplo = ehDuplo(); medir();
  var ps = par(atual);
  esp.innerHTML = duplo ? folha(ps[0], 'esq') + folha(ps[1], 'dir') : folha(ps[0], 'uni');
  $('#ldoc-ir').value = atual; $('.lt-prog i', ld).style.width = (atual / DOC.paginas * 100) + '%';
  var cap = null; (DOC.toc || []).forEach(function(c){ if(c.p && c.p <= atual) cap = c; });
  $('.tt', ld).textContent = cap ? cap.t : DOC.titulo;
  try{ localStorage.setItem('ldoc_' + DOC.base, atual); }catch(e){}
  [1, 2, 3, -1, -2].forEach(function(d){ var n = atual + d; if(n >= 1 && n <= DOC.paginas){ var im = new Image(); im.src = src(n); } });
  $$('.lt-miniaturas button', ld).forEach(function(b){ var n = +b.getAttribute('data-n'), on = ps.indexOf(n) >= 0; b.classList.toggle('on', on); if(on && $('.lt-miniaturas', ld).classList.contains('on')) b.scrollIntoView({ inline: 'center', block: 'nearest' }); });
}
function passo(){ return duplo ? 2 : 1; }
function ir(n, animar){
  n = Math.max(1, Math.min(DOC.paginas, n | 0));
  if(duplo) n = n === 1 ? 1 : (n % 2 === 0 ? n : n - 1);
  if(n === atual || animando){ if(n !== atual){ atual = n; render(); } return; }
  var dir = n > atual ? 1 : -1;
  if(animar && duplo && Math.abs(n - atual) <= 2 && !matchMedia('(prefers-reduced-motion: reduce)').matches){ virar(n, dir); return; }
  atual = n; pararFala(); render();
}
function virar(n, dir){
  animando = true; pararFala();
  var de = par(atual), para = par(n), frente = dir > 0 ? de[1] : de[0], verso = dir > 0 ? para[0] : para[1];
  var esqF = $('.folha.esq', esp), dirF = $('.folha.dir', esp);
  var v = document.createElement('div'); v.className = 'virando';
  v.style.left = (dir > 0 ? dirF.offsetLeft : esqF.offsetLeft) + 'px';
  v.style.transformOrigin = dir > 0 ? 'left center' : 'right center';
  v.innerHTML = '<div class="face"><img src="' + (frente ? src(frente) : '') + '" alt=""></div><div class="face verso"><img src="' + (verso ? src(verso) : '') + '" alt=""></div>';
  esp.appendChild(v);
  var alvo = dir > 0 ? $('img', dirF) : $('img', esqF), sob = dir > 0 ? para[1] : para[0];
  if(alvo){ if(sob) alvo.src = src(sob); else alvo.parentNode.classList.add('vazia'); }
  requestAnimationFrame(function(){ requestAnimationFrame(function(){ v.style.transform = 'rotateY(' + (dir > 0 ? -180 : 180) + 'deg)'; }); });
  setTimeout(function(){ atual = n; animando = false; render(); }, 760);
}
function ampliar(n){ var z = $('.lt-zoom', ld); $('img', z).src = src(n); z.classList.add('on'); z.scrollTop = 0; }
function fechar(){ ld.classList.remove('aberto'); document.documentElement.style.overflow = ''; pararFala(); $('.lt-zoom', ld).classList.remove('on'); $('.lt-painel', ld).classList.remove('on'); }
function painelSum(){
  var p = $('.lt-painel', ld);
  if(p.classList.contains('on') && p.dataset.modo === 'sum'){ p.classList.remove('on'); return; }
  p.dataset.modo = 'sum'; $('h4', p).textContent = t('sum'); $('.ps', p).style.display = 'none';
  var toc = (DOC.toc || []).filter(function(c){ return c.p; });
  $('.lt-res', p).innerHTML = toc.length ? toc.map(function(c){ return '<button data-p="' + c.p + '">' + esc(c.t) + ' <span style="float:right;color:var(--tx3)">' + c.p + '</span></button>'; }).join('') : '<p style="padding:12px;color:var(--tx3)">' + t('semsum') + '</p>';
  $$('.lt-res button', p).forEach(function(b){ b.addEventListener('click', function(){ ir(+b.getAttribute('data-p')); if(innerWidth < 700) p.classList.remove('on'); }); });
  p.classList.add('on');
}
function painelBus(){
  var p = $('.lt-painel', ld);
  if(p.classList.contains('on') && p.dataset.modo === 'bus'){ p.classList.remove('on'); return; }
  p.dataset.modo = 'bus'; $('h4', p).textContent = t('busca_t'); $('.ps', p).style.display = ''; $('.lt-res', p).innerHTML = '';
  p.classList.add('on'); carregarTexto(); setTimeout(function(){ $('input', p).focus(); }, 300);
}
function norm(s){ s = String(s || ''); var o = ''; for(var i = 0; i < s.length; i++) o += (s[i].normalize('NFD')[0] || s[i]).toLowerCase(); return o; }
function carregarTexto(cb){
  if(TEXTO){ cb && cb(); return; }
  var r = $('.lt-res', ld); if(!cb) r.innerHTML = '<p style="padding:12px;color:var(--tx3)">' + t('carregando') + '</p>';
  fetch(DOC.base + 'texto.json').then(function(x){ return x.json(); }).then(function(j){ TEXTO = j; TEXTO.n = TEXTO.map(norm); if(!cb) r.innerHTML = ''; cb && cb(); }).catch(function(){});
}
function buscar(q){
  if(!TEXTO) return carregarTexto(function(){ buscar(q); });
  var nq = norm(q).trim(), r = $('.lt-res', ld); if(nq.length < 3){ r.innerHTML = ''; return; }
  var res = [];
  for(var i = 0; i < TEXTO.length && res.length < 200; i++){ var tx = TEXTO.n[i], k = tx.indexOf(nq), c = 0; while(k >= 0 && c < 3){ res.push([i + 1, k]); c++; k = tx.indexOf(nq, k + nq.length); } }
  if(!res.length){ r.innerHTML = '<p style="padding:12px;color:var(--tx3)">' + t('sem') + '</p>'; return; }
  r.innerHTML = '<p style="padding:6px 10px;color:var(--tx3);font-size:.78rem">' + res.length + ' ' + t('res') + '</p>' + res.map(function(x){
    var o = TEXTO[x[0] - 1], a = Math.max(0, x[1] - 60), b = Math.min(o.length, x[1] + nq.length + 80), tr = o.slice(a, b).replace(/\s+/g, ' ');
    var ini = norm(tr).indexOf(nq); if(ini < 0) ini = 0;
    return '<button data-p="' + x[0] + '"><b>' + t('pagina') + ' ' + x[0] + '</b><br>' + (a > 0 ? '…' : '') + esc(tr.slice(0, ini)) + '<mark>' + esc(tr.slice(ini, ini + nq.length)) + '</mark>' + esc(tr.slice(ini + nq.length)) + '…</button>';
  }).join('');
  $$('button', r).forEach(function(b){ b.addEventListener('click', function(){ ir(+b.getAttribute('data-p')); if(innerWidth < 700) $('.lt-painel', ld).classList.remove('on'); }); });
}
var synth = window.speechSynthesis;
function voz(){ var vs = synth ? synth.getVoices() : []; return vs.filter(function(v){ return /^pt(-|_)BR/i.test(v.lang); })[0] || vs.filter(function(v){ return /^pt/i.test(v.lang); })[0] || null; }
function pararFala(){ falando = false; try{ synth && synth.cancel(); }catch(e){} if(ld){ $('.lt-ouvindo', ld).classList.remove('on'); $('[data-a="ouvir"]', ld).classList.remove('on'); } }
function falar(n){
  if(!synth || !falando) return;
  var tx = (TEXTO[n - 1] || '').replace(/-\n(\S)/g, '$1').replace(/\s+/g, ' ').trim();
  if(!tx){ if(n < DOC.paginas){ ir(n + 1); falar(n + 1); } else pararFala(); return; }
  var partes = tx.match(/[^.!?;:]+[.!?;:]*/g) || [tx], k = 0;
  (function prox(){
    if(!falando) return;
    if(k >= partes.length){ if(n < DOC.paginas){ ir(n + 1); falar(n + 1); } else pararFala(); return; }
    var u = new SpeechSynthesisUtterance(partes[k++]); u.lang = 'pt-BR'; var v = voz(); if(v) u.voice = v;
    u.onend = prox; u.onerror = pararFala; synth.speak(u);
  })();
}
function ouvir(){ if(!synth) return; if(falando){ pararFala(); return; } carregarTexto(function(){ falando = true; $('.lt-ouvindo', ld).classList.add('on'); $('[data-a="ouvir"]', ld).classList.add('on'); falar(par(atual).filter(Boolean)[0]); }); }
function abrirDoc(base, pdf){
  montarUI(); rotular();
  fetch(base + 'livro.json').then(function(r){ return r.json(); }).then(function(j){
    DOC = j; DOC.base = base; TEXTO = null;
    $('.tot', ld).textContent = '/ ' + DOC.paginas; $('#ldoc-ir').max = DOC.paginas;
    var bx = $('.lt-baixar', ld); if(pdf){ bx.href = pdf; bx.style.display = ''; } else bx.style.display = 'none';
    var h = ''; for(var i = 1; i <= DOC.paginas; i++) h += '<button data-n="' + i + '" aria-label="' + t('pagina') + ' ' + i + '"><img loading="lazy" src="' + src(i, true) + '" alt=""><span>' + i + '</span></button>';
    var m = $('.lt-miniaturas', ld); m.innerHTML = h; $$('button', m).forEach(function(b){ b.addEventListener('click', function(){ ir(+b.getAttribute('data-n')); }); });
    $('.lt-painel', ld).classList.remove('on');
    ld.classList.add('aberto'); document.documentElement.style.overflow = 'hidden';
    var salvo = 1; try{ salvo = +localStorage.getItem('ldoc_' + base) || 1; }catch(e){}
    atual = 0; ir(salvo, false);
    setTimeout(function(){ $('.lt-seta.prox', ld).focus(); }, 50);
  });
}
/* capas em livro 3D: inclinação com o ponteiro e abertura do leitor */
function ativar(){
  $$('.livro3d[data-doc]').forEach(function(lv){
    if(lv.dataset.pronto) return; lv.dataset.pronto = '1';
    var palco = lv.parentNode;
    palco.addEventListener('pointermove', function(e){ var r = palco.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5; lv.style.transform = 'rotateY(' + (-24 + x * 34) + 'deg) rotateX(' + (6 - y * 18) + 'deg)'; });
    palco.addEventListener('pointerleave', function(){ lv.style.transform = ''; });
    lv.addEventListener('click', function(){ abrirDoc(lv.getAttribute('data-doc'), lv.getAttribute('data-pdf')); });
  });
  $$('[data-abrir-doc]').forEach(function(b){ if(b.dataset.pronto) return; b.dataset.pronto = '1'; b.addEventListener('click', function(e){ e.preventDefault(); abrirDoc(b.getAttribute('data-abrir-doc'), b.getAttribute('data-pdf')); }); b.addEventListener('keydown', function(e){ if((e.key === 'Enter' || e.key === ' ') && b.tagName !== 'BUTTON' && b.tagName !== 'A'){ e.preventDefault(); b.click(); } }); });
}
window.LeitorICET = { abrir: abrirDoc, ativar: ativar };
if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ativar); else ativar();
})();
