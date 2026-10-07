document.addEventListener('DOMContentLoaded',()=>{
  const app=document.querySelector('#app');if(!app)return;
  const userBar=app.querySelector('.user-bar'),hero=app.querySelector('.hero'),upload=app.querySelector('.upload-panel'),method=app.querySelector('.method-section'),result=app.querySelector('#result'),weekly=app.querySelector('#weekly');
  if(!weekly)return;
  const nav=document.createElement('nav');nav.className='app-nav';nav.innerHTML='<button class="nav-link active" data-view="weekly-view" type="button">Radar cultural</button><button class="nav-link" data-view="trend-view" type="button">Evaluar un archivo</button>';
  const trend=document.createElement('section');trend.id='trend-view';trend.className='app-view hidden';[hero,upload,method,result].forEach(element=>element&&trend.appendChild(element));
  const radar=document.createElement('section');radar.id='weekly-view';radar.className='app-view';radar.appendChild(weekly);
  app.insertBefore(nav,userBar.nextSibling);app.append(trend,radar);
  function show(id){[trend,radar].forEach(view=>view.classList.toggle('hidden',view.id!==id));nav.querySelectorAll('.nav-link').forEach(button=>button.classList.toggle('active',button.dataset.view===id));window.scrollTo({top:0,behavior:'smooth'})}
  nav.querySelectorAll('.nav-link').forEach(button=>button.onclick=()=>show(button.dataset.view));
});
