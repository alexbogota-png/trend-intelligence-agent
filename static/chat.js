const weeklyConversation=[];
const chatEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const chatList=(title,items)=>items?.length?`<section class="chat-insight-section"><h4>${chatEscape(title)}</h4><ul>${items.map(item=>`<li>${chatEscape(item)}</li>`).join('')}</ul></section>`:'';
const connectionList=items=>Array.isArray(items)&&items.length?`<section class="chat-insight-section chat-connections"><h4>Conexiones con el portafolio</h4><ul>${items.map(item=>`<li><strong>${chatEscape(item?.marca||'Portafolio')}</strong><span>${chatEscape(item?.oportunidad||item?.relacion||'')}</span><small>${chatEscape(item?.fundamento||'')} · ${chatEscape(item?.nivel||'Hipótesis')}</small></li>`).join('')}</ul></section>`:'';
const trendBlock=trend=>trend?.nombre?`<section class="chat-insight-section chat-trend"><h4>Tendencia identificada</h4><p><strong>${chatEscape(trend.nombre)}</strong></p>${trend.descripcion?`<p>${chatEscape(trend.descripcion)}</p>`:''}${Array.isArray(trend.senales)&&trend.senales.length?`<ul>${trend.senales.map(item=>`<li>${chatEscape(item)}</li>`).join('')}</ul>`:''}</section>`:'';
const suggestionList=items=>Array.isArray(items)&&items.length?`<section class="chat-insight-section chat-suggestions"><h4>Puedes preguntar</h4><ul>${items.map(item=>`<li>${chatEscape(item)}</li>`).join('')}</ul></section>`:'';
const renderAnswer=answer=>{
  if(typeof answer==='string')return `<p>${chatEscape(answer)}</p>`;
  const isAnalytical=answer?.mostrar_analisis!==false;
  return `<div class="weekly-chat-answer"><section class="chat-insight-section chat-central"><h4>Respuesta directa</h4><p>${chatEscape(answer?.respuesta_directa||answer?.idea_central||'')}</p></section>${isAnalytical?`${trendBlock(answer?.tendencia)}${chatList('Evidencia',answer?.evidencia||answer?.que_vemos)}${chatList('Interpretación',answer?.interpretacion||answer?.que_significa)}${connectionList(answer?.conexiones_portafolio)}${chatList('Siguiente paso',answer?.accion||answer?.que_haria)}`:suggestionList(answer?.sugerencias)}<div class="chat-evidence-level">${chatEscape(answer?.nivel_evidencia||'')}</div></div>`;
};
const renderRanking=ranking=>ranking?.length?`<div class="chat-ranking"><h4>Top ${ranking.length} por interacciones</h4><ol>${ranking.map(item=>`<li><div><strong>${chatEscape(item.title)}</strong><small>${chatEscape(item.author)} · ${chatEscape(item.published_at)}</small></div><b>${Number(item.interactions||0).toLocaleString('es-CO')}</b></li>`).join('')}</ol></div>`:'';
const renderVisual=visual=>{
  if(!visual)return '';
  const max=Math.max(1,...(visual.bars||[]).map(item=>Number(item.value)||0));
  const metrics=(visual.metrics||[]).map(item=>`<div class="chat-metric"><span>${chatEscape(item.label)}</span><strong>${Number(item.value||0).toLocaleString('es-CO')}</strong></div>`).join('');
  const bars=(visual.bars||[]).map(item=>`<div class="chat-bar-row"><div class="chat-bar-label"><span>${chatEscape(item.label)}</span><strong>${chatEscape(item.value)}</strong></div><div class="chat-bar-track" role="progressbar" aria-label="${chatEscape(item.label)}" aria-valuenow="${Number(item.value)||0}" aria-valuemin="0" aria-valuemax="${max}"><span style="width:${Math.max(4,((Number(item.value)||0)/max)*100)}%"></span></div></div>`).join('');
  return `<div class="chat-visual"><h4>${chatEscape(visual.title||'Evidencia')}</h4><div class="chat-metrics">${metrics}</div>${bars?`<div class="chat-bars">${bars}</div>`:''}<small>${chatEscape(visual.note||'')}</small></div>`;
};
const renderAssistant=item=>`${renderAnswer(item.content)}${renderRanking(item.ranking)}${renderVisual(item.visual)}`;
function renderWeeklyChat(){
  const box=document.querySelector('#weekly-chat-messages');
  if(!box)return;
  box.innerHTML=weeklyConversation.length?weeklyConversation.map(item=>`<div class="weekly-chat-message ${item.role==='user'?'user':'assistant'}"><span>${item.role==='user'?'Tú':'Trend Agent'}</span>${item.role==='user'?`<p>${chatEscape(item.content)}</p>`:renderAssistant(item)}</div>`).join(''):'<div class="weekly-chat-empty">Aún no hay preguntas para esta semana.</div>';
  box.scrollTop=box.scrollHeight;
}
document.addEventListener('DOMContentLoaded',()=>{
  const form=document.querySelector('#weekly-chat-form');
  const input=document.querySelector('#weekly-chat-question');
  if(!form||!input)return;
  renderWeeklyChat();
  form.onsubmit=async event=>{
    event.preventDefault();
    const question=input.value.trim();
    const weekStart=document.querySelector('#week-start')?.value;
    if(!question||!weekStart)return;
    weeklyConversation.push({role:'user',content:question});
    renderWeeklyChat();
    input.value='';
    try{
      const token=window.getAccessToken?.()||'';
      const response=await fetch('/api/weekly/chat',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({market:'CO',week_start:weekStart,question,messages:weeklyConversation})});
      const text=await response.text();
      let data;try{data=JSON.parse(text)}catch{throw Error(`Error del servidor (${response.status}): ${text.slice(0,240)}`)}
      if(!response.ok)throw Error(data.detail||'No fue posible responder la pregunta.');
      weeklyConversation.push({role:'assistant',content:data.structured_answer||data.answer,ranking:data.ranking,visual:data.visual});
    }catch(error){weeklyConversation.push({role:'assistant',content:error.message})}
    renderWeeklyChat();
  };
  const reset=()=>{weeklyConversation.length=0;renderWeeklyChat()};
  document.querySelector('#week-start')?.addEventListener('change',reset);
  document.querySelector('#previous-week')?.addEventListener('click',reset);
  document.querySelector('#next-week')?.addEventListener('click',reset);
});
