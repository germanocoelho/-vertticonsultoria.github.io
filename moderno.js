/* VERTTI | camada de movimento 2026 */
(function(){
  var reduz = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // barra de progresso de leitura
  var bar = document.createElement('div'); bar.id = 'vprog'; document.body.appendChild(bar);
  var tick = false;
  function prog(){
    var h = document.documentElement.scrollHeight - innerHeight;
    bar.style.transform = 'scaleX(' + (h > 0 ? Math.min(1, scrollY / h) : 0) + ')';
    tick = false;
  }
  addEventListener('scroll', function(){ if(!tick){ tick = true; requestAnimationFrame(prog); } }, {passive:true});
  prog();

  // entrada do hero
  var heroEls = document.querySelectorAll('.hero-badges, .hero h1, .hero .lead, .hero-actions, .hero-stats, .hero-seal');
  heroEls.forEach(function(el, i){
    el.classList.add('m-entra');
    setTimeout(function(){ el.classList.add('ok'); }, reduz ? 0 : 250 + i * 140);
  });

  // revelações ao rolar
  var alvos = document.querySelectorAll('.banda .m-rev, .serv-foto.m-cortina');
  if('IntersectionObserver' in window && !reduz){
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('ok'); io.unobserve(e.target); } });
    }, {threshold:.18, rootMargin:'0px 0px -6% 0px'});
    alvos.forEach(function(el){ io.observe(el); });
  } else {
    alvos.forEach(function(el){ el.classList.add('ok'); });
  }

  if(reduz) return;

  // paralaxe com GSAP ScrollTrigger, quando disponível
  function paralaxe(){
    if(!window.gsap || !window.ScrollTrigger) return false;
    gsap.registerPlugin(ScrollTrigger);
    document.querySelectorAll('.banda').forEach(function(b){
      var img = b.querySelector('.banda-img');
      if(img) gsap.fromTo(img, {yPercent:-8}, {yPercent:8, ease:'none', scrollTrigger:{trigger:b, start:'top bottom', end:'bottom top', scrub:true}});
      var linha = b.querySelector('.banda-linha');
      if(linha) gsap.fromTo(linha, {scaleX:0}, {scaleX:1, duration:1.2, ease:'power3.out', scrollTrigger:{trigger:b, start:'top 70%'}});
    });
    document.querySelectorAll('.cta-final .m-fundo img').forEach(function(img){
      gsap.fromTo(img, {yPercent:-6}, {yPercent:6, ease:'none', scrollTrigger:{trigger:img.closest('section'), start:'top bottom', end:'bottom top', scrub:true}});
    });
    var hf = document.querySelector('.hero-foto');
    if(hf) gsap.to(hf, {yPercent:14, opacity:.55, ease:'none', scrollTrigger:{trigger:'.hero', start:'top top', end:'bottom top', scrub:true}});
    return true;
  }
  if(!paralaxe()) addEventListener('load', paralaxe);

  // botões magnéticos (apenas com mouse)
  if(matchMedia('(pointer:fine)').matches){
    document.querySelectorAll('.btn, .nav-cta').forEach(function(b){
      b.addEventListener('mousemove', function(ev){
        var r = b.getBoundingClientRect();
        var x = (ev.clientX - r.left - r.width/2) * .18, y = (ev.clientY - r.top - r.height/2) * .28;
        b.style.transform = 'translate(' + x + 'px,' + y + 'px)';
      });
      b.addEventListener('mouseleave', function(){ b.style.transform = ''; });
    });
  }
})();
