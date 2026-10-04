'use strict';
const $ = (selector) => document.querySelector(selector);
let token = '';
let pendingAction = null;
let currentView = 'overview';
let refreshing = false;
let toastTimeout;
const titles = {overview:['Deployment overview','A clear view of your releases, service health, and team priorities.'],releases:['Application releases','Follow every deployment and rollback in this environment.'],incidents:['Incident desk','Investigate service issues and document their resolution.'],board:['Team work board','Turn requirements into visible, manageable tasks.']};
function node(tag, className, value) { const element=document.createElement(tag); if(className) element.className=className; if(value!==undefined) element.textContent=value; return element; }
function pill(text, color='neutral') { return node('span',`pill ${color}`,text); }
function date(value) { return new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}); }
function empty(title, detail) { const element=node('div','empty'); element.append(node('strong','',title),node('span','',detail)); return element; }
function toast(message, failure=false) { const element=$('#toast'); element.textContent=message; element.classList.toggle('failure',failure); element.hidden=false; clearTimeout(toastTimeout); toastTimeout=setTimeout(()=>{element.hidden=true;},5000); }
async function api(path, method='GET', data) {
  const headers={}; if(token) headers.Authorization=`Bearer ${token}`; if(data) headers['Content-Type']='application/json';
  const response=await fetch(path,{method,headers,body:data?JSON.stringify(data):undefined,signal:AbortSignal.timeout(10000)});
  const result=await response.json(); if(!response.ok) throw new Error(result.error || `Request failed (${response.status})`); return result;
}
function requireAccess(action) { if(token) action(); else { pendingAction=action; $('#access-dialog').showModal(); } }
function setView(view) {
  currentView=view;
  document.querySelectorAll('[data-views]').forEach(element=>{element.hidden=!element.dataset.views.split(' ').includes(view);});
  document.querySelectorAll('[data-view]').forEach(element=>{element.classList.toggle('active',element.dataset.view===view);element.setAttribute('aria-current',element.dataset.view===view?'page':'false');});
  $('#page-title').textContent=titles[view][0]; $('#page-subtitle').textContent=titles[view][1];
  $('#breadcrumb-current').textContent={overview:'Overview',releases:'Releases',incidents:'Incident desk',board:'Work board'}[view];
}
function renderReleases(items) {
  const list=$('#release-list'); list.replaceChildren();
  if(!items.length) {list.append(empty('Your next release starts here.','Successful deployments record their version and image in this environment.'));return;}
  for(const item of items.slice(0,currentView==='releases'?100:4)) {
    const row=node('div','release-row'), main=node('div','release-main');
    main.append(node('strong','',item.version),node('small','',`${item.environment} · ${item.action.replaceAll('-',' ')}`));
    const time=node('time','',date(item.created_at));time.dateTime=item.created_at;
    row.append(node('span','release-icon',item.action==='rollback'?'↶':'↗'),main,pill(item.action==='rollback'?'RESTORED':'RECORDED','green'),time);list.append(row);
  }
}
function renderIncidents(items) {
  const body=$('#incident-list');body.replaceChildren();
  if(!items.length) {const cell=node('td','');cell.colSpan=5;cell.append(empty('No incidents recorded.','Report an observed issue to begin an investigation.'));const row=node('tr','');row.append(cell);body.append(row);return;}
  for(const item of items.slice(0,currentView==='incidents'?100:5)) {
    const row=node('tr',''), title=node('td','');title.append(node('span','incident-title',item.title),node('span','incident-sub',`INC-${String(item.id).padStart(3,'0')} · ${item.service}${item.demo?' · Example':''}`));
    const severity=node('td','');severity.append(pill(item.severity,item.severity==='SEV1'?'red':item.severity==='SEV2'?'amber':'neutral'));
    const status=node('td','');status.append(pill(item.status.toUpperCase(),item.status==='resolved'?'green':'amber'));
    const opened=node('td','',date(item.created_at)), action=node('td','');
    if(item.status!=='resolved') {const button=node('button','text-button',item.status==='open'?'Investigate':'Resolve');button.addEventListener('click',()=>requireAccess(async()=>{try{button.disabled=true;await api(`/api/incidents/${item.id}`,'PATCH',{status:item.status==='open'?'investigating':'resolved'});await refresh();toast('Incident updated');}catch(error){toast(error.message,true);}finally{button.disabled=false;}}));action.append(button);}else{action.textContent='Resolved';}
    row.append(title,severity,status,opened,action);body.append(row);
  }
}
function renderBoard(items) {
  const board=$('#board');board.replaceChildren();
  for(const [status,label] of [['backlog','BACKLOG'],['in-progress','IN PROGRESS'],['done','DONE']]) {
    const column=node('div','board-column'), heading=node('div','column-heading'), tasks=items.filter(item=>item.status===status);
    heading.append(node('span','',label),node('span','column-count',tasks.length));column.append(heading);
    for(const item of tasks.slice(0,currentView==='board'?100:4)) {
      const card=node('article','task-card'), top=node('div','task-top');top.append(node('span',`priority ${item.priority}`,`${item.priority.toUpperCase()} PRIORITY`),node('span','task-id',`#${item.id}`));
      const select=node('select','task-select');select.setAttribute('aria-label',`Status for ${item.title}`);
      for(const [value,text] of [['backlog','Backlog'],['in-progress','In progress'],['done','Done']]) {const option=node('option','',text);option.value=value;select.append(option);}select.value=item.status;
      select.addEventListener('change',()=>{const next=select.value;select.value=item.status;requireAccess(async()=>{try{select.disabled=true;await api(`/api/tasks/${item.id}`,'PATCH',{status:next});await refresh();toast('Task moved');}catch(error){toast(error.message,true);}finally{select.disabled=false;}});});
      card.append(top,node('div','task-title',item.title),node('div','task-owner',item.owner),select);if(item.demo)card.append(node('span','sample-label','Example task'));column.append(card);
    }
    if(!tasks.length)column.append(node('div','empty','No tasks yet'));board.append(column);
  }
}
function renderEvents(items) {
  const list=$('#event-list');list.replaceChildren();
  if(!items.length){list.append(empty('A fresh workspace.','New tasks, incident updates, and releases appear here.'));return;}
  for(const item of items.slice(0,5)){const event=node('div','event'), detail=node('div','');const time=node('time','',date(item.created_at));time.dateTime=item.created_at;detail.append(node('p','',item.message),time);event.append(node('span','event-dot'),detail);list.append(event);}
}
function renderChart(probes) {
  const area=$('#health-chart');area.replaceChildren();
  if(!probes.length){area.append(node('span','','Start the monitor to collect health observations.'));return;}
  const samples=probes.slice(-60), namespace='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(namespace,'svg');svg.setAttribute('viewBox','0 0 400 100');svg.setAttribute('role','img');svg.setAttribute('aria-label','Recent health check latency; red points indicate failed checks');
  const add=(tag,attributes)=>{const element=document.createElementNS(namespace,tag);Object.entries(attributes).forEach(([key,value])=>element.setAttribute(key,value));svg.append(element);return element;};
  for(const y of [15,50,85])add('line',{x1:0,y1:y,x2:400,y2:y,stroke:'#eaf0e2','stroke-dasharray':'3 5'});
  const maximum=Math.max(5,...samples.filter(item=>item.ok).map(item=>item.latency_ms));
  const points=samples.map((item,index)=>({x:samples.length===1?200:8+index*384/(samples.length-1),y:item.ok?85-item.latency_ms/maximum*65:90,item}));
  const path=points.map((point,index)=>`${index?'L':'M'}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
  add('path',{d:`${path} L${points.at(-1).x} 100 L${points[0].x} 100 Z`,fill:'#e9f3dd',opacity:'.7'});
  add('path',{d:path,fill:'none',stroke:'#82a966','stroke-width':'2'});
  for(const point of points){const dot=add('circle',{cx:point.x,cy:point.y,r:point.item.ok?'2.5':'4',fill:point.item.ok?'#699958':'#c6745d'});const title=document.createElementNS(namespace,'title');title.textContent=`${date(point.item.observed_at)}: ${point.item.ok?`${point.item.latency_ms.toFixed(1)} ms`:'Failed'}`;dot.append(title);}
  area.append(svg);$('#chart-from').textContent=date(samples[0].observed_at);$('#chart-to').textContent=date(samples.at(-1).observed_at);
}
let state;
function render(data) {
  state=data;$('#environment').textContent=data.environment.toUpperCase();$('#demo-banner').hidden=!data.demo;
  $('#health-value').textContent=data.health.status==='ready'?'Ready':'Unavailable';$('#health-value').classList.toggle('healthy',data.health.status==='ready');
  $('#health-note').textContent=data.health.status==='ready'?'Service and database responding':'Readiness check failed';
  $('#availability-value').textContent=data.observation.success_percent===null?'—':`${data.observation.success_percent.toFixed(2)}%`;
  $('#availability-note').textContent=`${data.observation.count} recorded checks · last 24 hours`;
  $('#incidents-value').textContent=data.counts.open_incidents;$('#incident-nav-count').textContent=data.counts.open_incidents;
  $('#releases-value').textContent=data.counts.releases;$('#version-note').textContent=`Current version ${data.version.slice(0,12)}`;
  $('#probe-count').textContent=`${data.observation.count} ${data.observation.count===1?'CHECK':'CHECKS'}`;$('#pending-count').textContent=`${data.counts.pending_tasks} PENDING`;
  $('#latency-value').textContent=data.observation.latency_ms===null?'—':`${data.observation.latency_ms} ms`;
  renderReleases(data.releases);renderIncidents(data.incidents);renderBoard(data.tasks);renderEvents(data.events);renderChart(data.probes);
  $('#footer-status').textContent=`${data.environment} · version ${data.version.slice(0,12)} · ${data.health.status}`;
  $('#footer-dot').className=data.health.status==='ready'?'green-dot':'';
  $('#updated-at').textContent=`Updated ${new Date().toLocaleTimeString()} · refreshes every 15s`;
}
async function refresh() {if(refreshing)return;refreshing=true;$('#refresh-button').disabled=true;try{render(await api('/api/state'));$('#connection-error').hidden=true;}catch(error){$('#connection-error').textContent=`Workspace unavailable. ${error.message}`;$('#connection-error').hidden=false;$('#footer-status').textContent='Connection unavailable';}finally{refreshing=false;$('#refresh-button').disabled=false;}}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{setView(button.dataset.view);if(state)render(state);}));
document.querySelectorAll('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$('#refresh-button').addEventListener('click',refresh);
function updateAccessState(){const label=token?'Lock editing':'Unlock editing';$('#access-label').textContent=label;$('#mobile-access-button').textContent=token?'Lock':'Unlock';$('#mobile-access-button').setAttribute('aria-label',label);}
function toggleAccess(){if(token){token='';updateAccessState();toast('Editing locked');}else{$('#access-dialog').showModal();}}
$('#access-button').addEventListener('click',toggleAccess);$('#mobile-access-button').addEventListener('click',toggleAccess);
$('#access-form').addEventListener('submit',async event=>{event.preventDefault();token=$('#operator-token').value;try{await api('/api/access');$('#operator-token').value='';$('#access-dialog').close();updateAccessState();toast('Editing unlocked');const action=pendingAction;pendingAction=null;if(action)action();}catch(error){token='';updateAccessState();toast('Operator token was not accepted',true);}});
$('#new-task-button').addEventListener('click',()=>requireAccess(()=>$('#task-dialog').showModal()));
$('#new-incident-button').addEventListener('click',()=>requireAccess(()=>$('#incident-dialog').showModal()));
for(const kind of ['task','incident']){$(`#${kind}-form`).addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('[type=submit]');button.disabled=true;try{await api(`/api/${kind==='task'?'tasks':'incidents'}`,'POST',Object.fromEntries(new FormData(form)));$(`#${kind}-dialog`).close();form.reset();await refresh();toast(kind==='task'?'Task created':'Incident reported');}catch(error){toast(error.message,true);}finally{button.disabled=false;}});}
setView('overview');refresh();setInterval(()=>{if(!document.hidden)refresh();},15000);
