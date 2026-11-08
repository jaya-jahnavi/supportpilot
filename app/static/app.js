'use strict';
const $=s=>document.querySelector(s);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const when=t=>new Date(t*1000).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
let tickets=[],selected=null,detailKey=null,listKey=null,page='inbox',timer=null,submissionKey=null;
async function api(url,options={}){
 const r=await fetch(url,{...options,headers:{'Content-Type':'application/json','X-SupportPilot-Request':'1',...options.headers}});
 if(!r.ok){let message='Request failed.';try{message=(await r.json()).detail||message;}catch{}if(r.status===401&&url!='/api/login')logoutUI();throw new Error(message);}
 return r.json();
}
function notice(text){$('#notice').textContent=text;$('#notice').hidden=!text;}
function logoutUI(){clearInterval(timer);timer=null;$('#workspace').hidden=true;$('#login').hidden=false;$('#password').value='';document.querySelectorAll('dialog[open]').forEach(d=>d.close());}
async function enter(){
 const me=await api('/api/me');$('#workspace').hidden=false;$('#login').hidden=true;
 $('#mode').textContent=me.llm_enabled?'LOCAL LLM ENABLED':'RETRIEVAL ONLY';
 selected=null;detailKey=null;listKey=null;await refresh();clearInterval(timer);
 timer=setInterval(()=>{if(!document.hidden)refresh().catch(e=>notice(e.message));},2000);
}
$('#login-form').addEventListener('submit',async e=>{
 e.preventDefault();const b=$('#login-form button');b.disabled=true;$('#login-error').textContent='';
 try{await api('/api/login',{method:'POST',body:JSON.stringify({email:$('#email').value,password:$('#password').value})});await enter();}catch(error){$('#login-error').textContent=error.message;}finally{b.disabled=false;}
});
$('#logout').addEventListener('click',async()=>{try{await api('/api/logout',{method:'POST'});logoutUI();}catch(e){notice(e.message);}});
function changePage(next){
 page=next;['inbox','knowledge','activity'].forEach(p=>$('#'+p+'-page').hidden=p!==page);
 document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
 $('#breadcrumb').textContent={inbox:'Inbox',knowledge:'Knowledge base',activity:'Activity'}[page];
 $('#page-title').textContent={inbox:'Better replies, less friction.',knowledge:'A good reply starts here.',activity:'Every step, accounted for.'}[page];
 $('#page-subtitle').textContent={inbox:'A focused space to turn incoming requests into thoughtful, grounded drafts.',knowledge:'The policy evidence behind every suggested response.',activity:'Trace requests through retrieval, generation, and human review.'}[page];
 if(page==='knowledge')loadKnowledge().catch(e=>notice(e.message));
}
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>changePage(b.dataset.page)));
async function refresh(){
 const [rows,ops]=await Promise.all([api('/api/tickets'),api('/api/operations')]);tickets=rows;notice('');
 $('#nav-count').textContent=rows.length;$('#total-stat').textContent=rows.length;
 $('#ready-stat').textContent=rows.filter(r=>r.status==='ready').length;$('#approved-stat').textContent=rows.filter(r=>r.status==='approved').length;
 $('#worker-light').classList.toggle('alive',ops.workers>0);$('#worker-label').textContent=ops.workers?'Worker online':'Worker offline';
 $('#activity-body').innerHTML=ops.events.map(e=>'<tr><td>'+esc(when(e.created))+'</td><td>'+esc(e.action)+'</td><td>'+esc(e.ticket_id?.slice(0,8)||'—')+'</td></tr>').join('');
 if(!selected&&rows.length)selected=rows[0].id;
 renderList();if(selected)await renderDetail(selected);
}
function renderList(){
 const status=$('#filter').value,filtered=tickets.filter(t=>!status||t.status===status);
 const html=filtered.map(t=>'<button class="ticket-item '+(t.id===selected?'active':'')+'" data-ticket="'+t.id+'"><strong>'+esc(t.subject)+'</strong><p>'+esc(t.body)+'</p><div class="ticket-meta"><span class="badge '+t.status+'">'+t.status+'</span><span>'+esc(when(t.created))+'</span></div></button>').join('');
 if(listKey!==html){$('#ticket-list').innerHTML=html;listKey=html;}
 $('#empty-list').hidden=filtered.length>0;$('#empty-list h3').textContent=tickets.length?'No matching requests.':'Your next conversation starts here.';
}
$('#filter').addEventListener('change',renderList);
$('#ticket-list').addEventListener('click',async e=>{
 const b=e.target.closest('[data-ticket]');if(!b)return;selected=b.dataset.ticket;detailKey=null;renderList();try{await renderDetail(selected);}catch(error){notice(error.message);}
});
async function renderDetail(id){
 const t=await api('/api/tickets/'+id);
 const key=JSON.stringify([t.id,t.version,t.status,t.error,t.attempts]);if(key===detailKey)return;detailKey=key;
 $('#detail-empty').hidden=true;$('#ticket-detail').hidden=false;
 let html='<div class="detail-head"><span class="badge '+t.status+'">'+t.status+'</span><h2>'+esc(t.subject)+'</h2><p>REQUEST '+t.id.slice(0,8)+' · '+esc(when(t.created))+' · Attempt '+t.attempts+' / 2</p></div><div class="request-body"><span>CUSTOMER REQUEST</span><p>'+esc(t.body)+'</p></div><div class="draft-section">';
 if(t.draft){
  const d=t.draft;
  html+='<div class="draft-head"><span>'+(d.mode==='llm'?'AI ASSISTED DRAFT':d.mode==='retrieval_only'?'RETRIEVED POLICY EXCERPTS':'MORE INFORMATION NEEDED')+'</span><small>'+esc(d.category)+' · '+esc(d.priority)+' priority</small></div><textarea id="reply" aria-label="Draft reply" maxlength="2400" rows="7" '+(t.status!=='ready'?'readonly':'')+'>'+esc(d.reply)+'</textarea><p class="review-helper">Check facts, policy fit, tone, and commitments before approval. Approval records your review locally and does not send a message.</p>'+(d.warnings?.length?'<p class="notice">Heuristic review flags: '+d.warnings.map(esc).join(' ')+'</p>':'')+'<h3>Supporting evidence</h3><div class="source-list">'+d.sources.map(s=>'<details><summary>'+esc(s.id)+' · '+esc(s.title)+(d.citations.includes(s.id)?' · cited':'')+'</summary><p>'+esc(s.body)+'</p></details>').join('')+'</div><div class="trace"><h3>Processing trace</h3>'+t.trace.map(s=>'<div><strong>'+esc(s.step.replaceAll('_',' '))+'</strong><span>'+esc(s.method||s.mode)+' '+(s.seconds!=null?'· '+s.seconds+'s':'')+'</span></div>').join('')+'<div><span>Prompt version</span><span>'+esc(d.prompt_version)+'</span></div><div><span>Model</span><span>'+esc(d.model||'No LLM used')+'</span></div></div>';
  if(t.status==='ready')html+='<div class="review-actions"><button class="secondary" id="reject">Reject draft</button><button class="primary" id="approve">Approve reviewed reply ✓</button></div>';
 }else{
  html+='<div class="empty"><span>✧</span><h3>'+(t.status==='failed'?'Drafting needs attention.':'Finding the right context.')+'</h3><p>'+esc(t.error||'The worker will retrieve policy evidence and prepare the draft. This view updates automatically.')+'</p>'+(t.status==='failed'?'<button id="retry" class="secondary">Retry request →</button>':'')+'</div>';
 }
 $('#ticket-detail').innerHTML=html+'</div>';
 ['approve','reject'].forEach(action=>{
  const b=$('#'+action);if(!b)return;b.addEventListener('click',async()=>{b.disabled=true;try{await api('/api/tickets/'+id+'/review',{method:'POST',body:JSON.stringify({action,expected_version:t.version,reply:$('#reply').value})});detailKey=null;await refresh();}catch(error){notice(error.message);b.disabled=false;}});
 });
 const retry=$('#retry');if(retry)retry.addEventListener('click',async()=>{try{await api('/api/tickets/'+id+'/retry',{method:'POST'});detailKey=null;await refresh();}catch(e){notice(e.message);}});
}
function openTicket(sample=false){
 submissionKey=crypto.randomUUID();$('#ticket-form').reset();$('#create-error').textContent='';
 if(sample)sampleReturn();$('#new-dialog').showModal();
}
function sampleReturn(){$('#subject').value='Return an unused product';$('#body').value='I received my order last week. The item is unused and I would like to return it. What should I do next?';}
$('#new-ticket').addEventListener('click',()=>openTicket());$('#sample-ticket').addEventListener('click',()=>openTicket(true));
$('#sample-return').addEventListener('click',sampleReturn);
$('#sample-security').addEventListener('click',()=>{$('#subject').value='Unauthorized login to my account';$('#body').value='I noticed an unauthorized login to my account. I need help securing access and changing my password.';});
document.querySelectorAll('.close').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
$('#ticket-form').addEventListener('submit',async e=>{
 e.preventDefault();$('#create-button').disabled=true;$('#create-error').textContent='';
 try{const t=await api('/api/tickets',{method:'POST',headers:{'Idempotency-Key':submissionKey},body:JSON.stringify({subject:$('#subject').value,body:$('#body').value})});selected=t.id;detailKey=null;$('#new-dialog').close();changePage('inbox');await refresh();}
 catch(error){$('#create-error').textContent=error.message;}finally{$('#create-button').disabled=false;}
});
async function loadKnowledge(){
 const q=$('#knowledge-query').value;
 const rows=await api('/api/knowledge'+(q?'?q='+encodeURIComponent(q):''));
 $('#knowledge-grid').innerHTML=rows.map(s=>'<article class="knowledge-card"><small>'+esc(s.id)+'</small><h2>'+esc(s.title)+'</h2><p>'+esc(s.body)+'</p></article>').join('')||'<div class="empty"><h3>No policy matches.</h3></div>';
}
$('#knowledge-form').addEventListener('submit',e=>{e.preventDefault();loadKnowledge().catch(error=>notice(error.message));});
enter().catch(()=>logoutUI());
