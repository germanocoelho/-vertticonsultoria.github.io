/* VERTTI | Abertura "O selo do registro"
   Uma prancha técnica de patente se desenha, os símbolos da propriedade intelectual
   se sucedem no centro, o anel do selo gira com as áreas de atuação e o carimbo
   é aplicado, revelando a marca. A tela se abre como uma pasta de documentos. */
(function(){
  var reduz = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var css = [
  '#vt-ab{position:fixed;inset:0;z-index:99999;display:grid;place-items:center;cursor:pointer;overflow:hidden}',
  '#vt-ab .meia{position:absolute;left:0;right:0;height:50.5%;background:#0B1F28;transition:transform 1.05s cubic-bezier(.75,0,.2,1)}',
  '#vt-ab .meia.c{top:0;border-bottom:1px solid rgba(201,162,75,.0)}#vt-ab .meia.b{bottom:0}',
  '#vt-ab.sai .meia.c{transform:translateY(-101%)}#vt-ab.sai .meia.b{transform:translateY(101%)}',
  '#vt-ab .meia.c:after,#vt-ab .meia.b:after{content:"";position:absolute;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,#C9A24B,transparent);opacity:0;transition:opacity .3s}',
  '#vt-ab .meia.c:after{bottom:0}#vt-ab .meia.b:after{top:0}',
  '#vt-ab.sai .meia.c:after,#vt-ab.sai .meia.b:after{opacity:1}',
  '#vt-ab .prancha{position:absolute;inset:0;width:100%;height:100%;opacity:.5}',
  '#vt-ab .prancha path,#vt-ab .prancha line,#vt-ab .prancha circle{fill:none;stroke:#2c5a6d;stroke-width:1;stroke-dasharray:1400;stroke-dashoffset:1400;animation:vtTraco 2.2s ease forwards}',
  '#vt-ab .prancha .g{stroke:#C9A24B;opacity:.55}',
  '#vt-ab.sai .prancha{opacity:0;transition:opacity .3s}',
  '@keyframes vtTraco{to{stroke-dashoffset:0}}@keyframes vtOp{to{opacity:1}}',
  '#vt-ab .palco{position:relative;display:grid;justify-items:center;gap:18px;transition:opacity .45s,transform .9s cubic-bezier(.7,0,.2,1)}',
  '#vt-ab.sai .palco{opacity:0;transform:scale(1.25)}',
  '#vt-ab svg.selo{width:min(360px,76vw);overflow:visible}',
  '#vt-ab .anel{fill:none;stroke:#C9A24B;stroke-width:2;stroke-dasharray:950;stroke-dashoffset:950;animation:vtTraco 1.2s cubic-bezier(.6,0,.2,1) .5s forwards}',
  '#vt-ab .anel2{fill:none;stroke:#C9A24B;stroke-width:.8;stroke-dasharray:3 5;opacity:0;animation:vtOp .6s ease 1.2s forwards}',
  '#vt-ab .giro{transform-origin:0 0;animation:vtGira 18s linear infinite}',
  '@keyframes vtGira{to{transform:rotate(360deg)}}',
  '#vt-ab .giro text{font:600 11.5px Inter,system-ui,sans-serif;letter-spacing:3.2px;fill:#E3C77E;opacity:0;animation:vtOp .8s ease 1.3s forwards}',
  '#vt-ab .simb{font-family:Fraunces,Georgia,serif;font-size:96px;font-weight:600;fill:#F6F2E9;text-anchor:middle;dominant-baseline:central;opacity:0;transform-box:fill-box;transform-origin:center}',
  '#vt-ab .s1{animation:vtSimb .75s ease .7s forwards}#vt-ab .s2{animation:vtSimb .75s ease 1.35s forwards}#vt-ab .s3{animation:vtSimb .75s ease 2s forwards}',
  '@keyframes vtSimb{0%{opacity:0;transform:scale(.6) rotate(-12deg)}35%,65%{opacity:1;transform:none}100%{opacity:0;transform:scale(1.4);filter:blur(4px)}}',
  '#vt-ab .carimbo{transform-box:fill-box;transform-origin:center;opacity:0;transform:scale(2.4);animation:vtCarimbo .55s cubic-bezier(.6,0,.3,1.4) 2.65s forwards}',
  '@keyframes vtCarimbo{to{opacity:1;transform:none}}',
  '#vt-ab .onda{fill:none;stroke:#E3C77E;stroke-width:3;opacity:0;transform-box:fill-box;transform-origin:center;animation:vtOnda 1s ease-out 3.05s forwards}',
  '@keyframes vtOnda{0%{opacity:.9;transform:scale(.8)}to{opacity:0;transform:scale(1.9)}}',
  '#vt-ab .tremor{animation:vtTreme .35s ease 3.05s}',
  '@keyframes vtTreme{25%{transform:translate(3px,-2px)}50%{transform:translate(-3px,2px)}75%{transform:translate(2px,1px)}}',
  '#vt-ab .nome{text-align:center;opacity:0;transform:translateY(14px);animation:vtNome .9s ease 3.25s forwards}',
  '@keyframes vtNome{to{opacity:1;transform:none}}',
  '#vt-ab .nome b{display:block;font-family:Fraunces,Georgia,serif;font-size:clamp(1.9rem,5.4vw,3rem);font-weight:600;letter-spacing:.2em;padding-left:.2em;color:#F6F2E9}',
  '#vt-ab .nome b em{font-style:normal;color:#E3C77E}',
  '#vt-ab .nome span{display:block;margin-top:8px;font:500 clamp(.64rem,1.6vw,.78rem)/1.4 Inter,system-ui,sans-serif;letter-spacing:.3em;text-transform:uppercase;color:rgba(246,242,233,.7)}',
  '#vt-ab .pular{position:absolute;bottom:22px;right:24px;font:600 .62rem/1 Inter,system-ui,sans-serif;letter-spacing:.2em;text-transform:uppercase;color:rgba(246,242,233,.45);transition:opacity .3s}',
  '#vt-ab.sai .pular{opacity:0}',
  '@media (prefers-reduced-motion:reduce){#vt-ab *{animation-duration:.01s!important;animation-delay:0s!important}}'
  ].join('\n');
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // prancha técnica: linhas de cota, engrenagem e retículas, como um desenho de patente
  var pr = '<svg class="prancha" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">';
  for(var x = 80; x < 1600; x += 120) pr += '<line x1="' + x + '" y1="0" x2="' + x + '" y2="900" style="animation-delay:' + (x / 4000).toFixed(2) + 's"/>';
  for(var y = 60; y < 900; y += 120) pr += '<line x1="0" y1="' + y + '" x2="1600" y2="' + y + '" style="animation-delay:' + (y / 3000).toFixed(2) + 's"/>';
  pr += '<circle class="g" cx="230" cy="690" r="110" style="animation-delay:.4s"/><circle class="g" cx="230" cy="690" r="60" style="animation-delay:.6s"/>';
  pr += '<path class="g" d="M1220 140 h260 v160 h-260z M1220 220 h260 M1350 140 v160" style="animation-delay:.5s"/>';
  pr += '<path class="g" d="M120 120 l90 0 M120 112 v16 M210 112 v16 M1300 760 l180 0 M1300 752 v16 M1480 752 v16" style="animation-delay:.8s"/></svg>';

  var html = '<div id="vt-ab" aria-hidden="true"><div class="meia c"></div><div class="meia b"></div>' + pr +
    '<div class="palco"><svg class="selo" viewBox="-180 -180 360 360"><defs><path id="vtCirc" d="M0 -132 A132 132 0 1 1 0 132 A132 132 0 1 1 0 -132"/></defs>' +
    '<g class="tremor"><circle class="anel" r="150"/><circle class="anel2" r="116"/>' +
    '<g class="giro"><text><textPath href="#vtCirc" textLength="826" lengthAdjust="spacing">MARCAS ◆ PATENTES ◆ SOFTWARE ◆ CONTRATOS ◆ INDICAÇÕES GEOGRÁFICAS ◆ INOVAÇÃO ◆</textPath></text></g>' +
    '<text class="simb s1" x="0" y="0">®</text><text class="simb s2" x="0" y="0">™</text><text class="simb s3" x="0" y="0">©</text>' +
    '<g class="carimbo"><circle r="104" fill="#F6F2E9"/><circle r="97" fill="none" stroke="#C9A24B" stroke-width="1.5"/>' +
    '<image href="foto/vertti-logo.webp" x="-84" y="-38" width="168" height="76"/></g>' +
    '<circle class="onda" r="104"/></g></svg>' +
    '<div class="nome"><b>VERTTI <em>CONSULTORIA</em></b><span>Propriedade Intelectual e Inovação</span></div></div>' +
    '<span class="pular">toque para entrar</span></div>';

  function abrir(){
    var velho = document.getElementById('vt-ab'); if(velho) velho.remove();
    var t = document.createElement('div'); t.innerHTML = html; var ab = t.firstElementChild;
    document.body.insertBefore(ab, document.body.firstChild);
    document.documentElement.style.overflow = 'hidden';
    var feito = false;
    function fim(){
      if(feito) return; feito = true; ab.classList.add('sai');
      document.documentElement.style.overflow = '';
      window.dispatchEvent(new Event('abertura-fim'));
      setTimeout(function(){ ab.remove(); }, 1300);
    }
    setTimeout(fim, reduz ? 600 : 4900);
    ab.addEventListener('click', fim);
  }
  abrir();
  addEventListener('pageshow', function(e){ if(e.persisted) abrir(); });
})();
