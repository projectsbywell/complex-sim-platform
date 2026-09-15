/* ComplexSim frontend — REST+WS client + offline local engines + canvas renderer */
'use strict';
/* ---------- API base (configurável: ?api= > localStorage > localhost) ---------- */
let API = 'http://localhost:8000';
try {
  const q = new URLSearchParams(location.search).get('api');
  const saved = localStorage.getItem('sim-api');
  if (q) { API = q.replace(/\/$/, ''); localStorage.setItem('sim-api', API); }
  else if (saved) API = saved;
} catch (e) {}
function wsBase() { return API.replace(/^http/, 'ws'); }
const KINDS = ['particles','fluids','physics','neural','bio'];
const DEFAULTS = {
  particles:{n:200,gravity:9.8,damping:0.99,restitution:0.8,seed:42},
  fluids:{size:32,viscosity:0.1,diffusion:0.01,seed:7},
  physics:{n:12,gravity:9.8,friction:0.2,restitution:0.7,seed:3},
  neural:{layers:[4,8,1],activation:'relu',seed:1},
  bio:{model:'sir',beta:0.3,gamma:0.08,seed:42}
};
let currentKind='particles', simId=null, token=null, running=false, raf=null;
let remote=true; // try backend, fallback local

/* ---------- i18n ---------- */
const STR={ 'pt-BR':{kinds:'Simulações',actions:'Ações',run:'Executar',pause:'Pausar'}, en:{kinds:'Simulations',actions:'Actions',run:'Run',pause:'Pause'} };
let lang=navigator.language.startsWith('pt')?'pt-BR':'en';
async function setLang(l){ lang=l; try{ const r=await fetch(`i18n/${l}.json`); if(r.ok){ window.I18N=await r.json(); } }catch(e){} document.documentElement.lang=l; document.querySelectorAll('[data-i18n]').forEach(el=>{ const k=el.getAttribute('data-i18n'); if(window.I18N&&window.I18N[k]) el.textContent=window.I18N[k]; }); renderLangButtons(); }
function renderLangButtons(){ const box=document.getElementById('lang-selector'); box.innerHTML=''; ['pt-BR','en','es','fr','de','ja','zh-CN'].forEach(l=>{ const b=document.createElement('button'); b.textContent=l; if(l===lang)b.classList.add('active'); b.onclick=()=>setLang(l); box.appendChild(b); }); }

/* ---------- local engines (offline fallback) ---------- */
function mulberry(seed){ return function(){ seed|=0; seed=seed+0x6D2B79F5|0; let t=Math.imul(seed^seed>>>15,1|seed); t=t+Math.imul(t^t>>>7,61|t)^t; return ((t^t>>>14)>>>0)/4294967296; }; }
class LocalEngine{
  constructor(kind,params){ this.kind=kind; this.params={...(DEFAULTS[kind]||{}),...(params||{})}; this.t=0; this.init(); }
  init(){ const p=this.params, rnd=mulberry(p.seed||1);
    if(this.kind==='particles'){ this.pos=Array.from({length:p.n},()=>[rnd()*900,rnd()*500]); this.vel=Array.from({length:p.n},()=>[ (rnd()-.5)*60,(rnd()-.5)*60]); }
    if(this.kind==='physics'){ this.bodies=Array.from({length:p.n||12},(_,i)=>({x:100+rnd()*700,y:60+rnd()*200,vx:(rnd()-.5)*80,vy:0,r:8+rnd()*14,m:1})); }
    if(this.kind==='fluids'){ const s=p.size||32; this.grid=new Float32Array(s*s).map(()=>rnd()*0.6); this.s=s; }
    if(this.kind==='neural'){ this.loss=[1.0]; }
    if(this.kind==='bio'){ const m=p.model||'sir'; if(m==='sir'){this.S=990;this.I=10;this.R=0;this.hist=[{S:990,I:10,R:0}];} else {this.prey=40;this.pred=9;this.hist=[{prey:40,pred:9}];} }
  }
  step(dt){ const p=this.params; this.t+=dt;
    if(this.kind==='particles'){ for(let i=0;i<this.pos.length;i++){ this.vel[i][1]+= (p.gravity||9.8)*dt*10; this.vel[i][0]*=p.damping; this.vel[i][1]*=p.damping; this.pos[i][0]+=this.vel[i][0]*dt; this.pos[i][1]+=this.vel[i][1]*dt; if(this.pos[i][1]>505){this.pos[i][1]=505;this.vel[i][1]*=-(p.restitution||0.8);} if(this.pos[i][0]<0||this.pos[i][0]>900) this.vel[i][0]*=-1; this.pos[i][0]=Math.max(0,Math.min(900,this.pos[i][0])); } }
    if(this.kind==='physics'){ for(const b of this.bodies){ b.vy+=(p.gravity||9.8)*dt*10; b.vx*=(1-(p.friction||0.2)*dt); b.x+=b.vx*dt; b.y+=b.vy*dt; if(b.y>505-b.r){b.y=505-b.r;b.vy*=-(p.restitution||0.7);} if(b.x<b.r||b.x>900-b.r){b.vx*=-(p.restitution||0.7);b.x=Math.max(b.r,Math.min(900-b.r,b.x));} } }
    if(this.kind==='fluids'){ for(let i=0;i<this.grid.length;i++){ this.grid[i]=this.grid[i]*0.995 + Math.random()*0.01; } }
    if(this.kind==='neural'){ const l=this.loss[this.loss.length-1]; this.loss.push(Math.max(0.001,l*0.985)); if(this.loss.length>200)this.loss.shift(); }
    if(this.kind==='bio'){ const m=p.model||'sir'; if(m==='sir'){ const N=this.S+this.I+this.R, b=p.beta||0.3, g=p.gamma||0.08; const nI=b*this.S*this.I/N*dt*10, nR=g*this.I*dt*10; this.S-=nI;this.I+=nI-nR;this.R+=nR; this.hist.push({S:this.S,I:this.I,R:this.R}); } else { const a=0.1,b2=0.02,c=0.3,d=0.01; const dn=this.prey*a*dt - b2*this.prey*this.pred*dt, dm=-this.pred*c*dt+d*this.prey*this.pred*dt; this.prey=Math.max(1,this.prey+dn*10); this.pred=Math.max(1,this.pred+dm*10); this.hist.push({prey:this.prey,pred:this.pred}); } if(this.hist.length>400)this.hist.shift(); }
  }
  getState(){ if(this.kind==='particles')return{positions:this.pos,step:Math.round(this.t*60)}; if(this.kind==='physics')return{bodies:this.bodies,step:Math.round(this.t*60)}; if(this.kind==='fluids')return{density:Array.from(this.grid.slice(0,512)),size:this.s,step:Math.round(this.t*60)}; if(this.kind==='neural')return{loss_history:this.loss,step:this.loss.length}; const m=this.params.model||'sir'; if(m==='sir')return{S:this.S,I:this.I,R:this.R,history:this.hist.slice(-50)}; return{prey:this.prey,pred:this.pred,history:this.hist.slice(-50)}; }
}
let local=new LocalEngine(currentKind,DEFAULTS[currentKind]);

/* ---------- backend client ---------- */
async function api(path,opts={}){ const h=opts.headers||{}; if(token)h['Authorization']='Bearer '+token; const r=await fetch(API+path,{...opts,headers:{'Content-Type':'application/json',...h}}); if(!r.ok)throw new Error('HTTP '+r.status); return r.json(); }
let ws=null;
function connectWS(){ if(!simId||!token)return; try{ ws=new WebSocket(`${wsBase()}/ws/simulations/${simId}?token=${token}`); ws.onmessage=e=>{ try{ const s=JSON.parse(e.data); if(s.state)renderState(s.state); }catch(_){} }; }catch(e){} }
async function ensureRemote(){ if(!token){remote=false;return false;} try{ const s=await api('/api/simulations',{method:'POST',body:JSON.stringify({kind:currentKind,params:local.params})}); simId=s.id; connectWS(); remote=true; return true; }catch(e){ remote=false; return false; } }

/* ---------- renderer ---------- */
const cv=document.getElementById('simulation-canvas'), ctx=cv.getContext('2d');
const chart=document.getElementById('chart-canvas'), cctx=chart.getContext('2d');
function renderState(st){ requestAnimationFrame(()=>draw(st)); updateStats(st); }
function draw(st){
  ctx.fillStyle=getComputedStyle(document.body).getPropertyValue('--card-bg')||'#111'; ctx.fillRect(0,0,cv.width,cv.height);
  if(currentKind==='particles'){ const P=st.positions||[]; ctx.fillStyle='#3498db'; for(const p of P){ ctx.beginPath(); ctx.arc(p[0]*(cv.width/900),p[1]*(cv.height/520),2.5,0,7); ctx.fill(); } }
  else if(currentKind==='physics'){ const B=st.bodies||[]; ctx.fillStyle='#e74c3c'; for(const b of B){ ctx.beginPath(); ctx.arc(b.x*(cv.width/900),b.y*(cv.height/520),(b.r||10)*(cv.width/900),0,7); ctx.fill(); ctx.strokeStyle='#fff'; ctx.stroke(); } }
  else if(currentKind==='fluids'){ const d=st.density||[]; const n=Math.ceil(Math.sqrt(d.length*2))||16; const cw=cv.width/n, ch=cv.height/n; for(let i=0;i<d.length;i++){ const v=Math.min(1,d[i]); ctx.fillStyle=`rgba(52,152,219,${v})`; ctx.fillRect((i%n)*cw,Math.floor(i/n)*ch,cw,ch); } }
  else if(currentKind==='neural'){ const L=st.loss_history||[1]; drawCurve(cctx,L,'#27ae60'); ctx.fillStyle='#fff'; ctx.font='16px sans-serif'; ctx.fillText('loss: '+L[L.length-1].toFixed(4),20,30); }
  else if(currentKind==='bio'){ const h=st.history||[]; drawBio(cctx,h); ctx.fillStyle='#fff'; ctx.font='14px sans-serif'; if(st.S!==undefined)ctx.fillText(`S=${st.S.toFixed(0)} I=${st.I.toFixed(0)} R=${st.R.toFixed(0)}`,20,30); else ctx.fillText(`prey=${(st.prey||0).toFixed(1)} pred=${(st.pred||0).toFixed(1)}`,20,30); }
}
function drawCurve(c,arr,color){ c.clearRect(0,0,chart.width,chart.height); c.strokeStyle=color; c.beginPath(); const m=Math.max(...arr,1e-6); arr.forEach((v,i)=>{ const x=i/Math.max(1,arr.length-1)*chart.width, y=chart.height-10-(v/m)*(chart.height-20); i?c.lineTo(x,y):c.moveTo(x,y); }); c.stroke(); }
function drawBio(c,h){ c.clearRect(0,0,chart.width,chart.height); if(!h.length)return; const keys=Object.keys(h[0]); const colors={S:'#3498db',I:'#e74c3c',R:'#27ae60',prey:'#27ae60',pred:'#e74c3c'}; keys.forEach(k=>{ const arr=h.map(o=>o[k]); const m=Math.max(...arr,1); c.strokeStyle=colors[k]||'#fff'; c.beginPath(); arr.forEach((v,i)=>{ const x=i/Math.max(1,arr.length-1)*chart.width, y=chart.height-10-(v/m)*(chart.height-20); i?c.lineTo(x,y):c.moveTo(x,y); }); c.stroke(); }); }
function updateStats(st){ document.getElementById('stats-box').textContent=`kind=${currentKind} step=${st.step||0} t=${local.t.toFixed(2)}s ${remote?'• remote':'• local'}`; document.getElementById('status-box').textContent=(remote?'🟢 backend ':'🔴 offline ')+(token?'• auth':'• anon'); }

/* ---------- params panel ---------- */
function renderParams(){ const row=document.getElementById('params-row'); row.innerHTML=''; const p=local.params; Object.keys(p).forEach(k=>{ if(k==='layers'||k==='model'){ const w=document.createElement('div'); w.innerHTML=`<label class="param-label">${k}</label>`; const inp=document.createElement('input'); inp.value=p[k]; inp.style.width='100%'; inp.onchange=()=>{ local.params[k]=k==='model'?inp.value:JSON.parse(inp.value); syncParams(); }; w.appendChild(inp); row.appendChild(w); return; } const v=p[k]; const w=document.createElement('div'); const mn=0, mx=(k==='n'||k==='size')?500:(typeof v==='number'&&v<2?1:20); w.innerHTML=`<label class="param-label">${k}: <b id="pv-${k}">${v}</b></label>`; const s=document.createElement('input'); s.type='range'; s.min=mn; s.max=mx; s.step=(mx-mn)/100; s.value=v; s.className='param-control'; s.oninput=()=>{ const nv=parseFloat(s.value); local.params[k]=(k==='n'||k==='size'||k==='seed')?Math.round(nv):nv; document.getElementById('pv-'+k).textContent=local.params[k]; syncParams(); }; w.appendChild(s); row.appendChild(w); }); }
/* Sem endpoint de update de params no backend: o remoto é recriado ao trocar de kind.
   Slider move só o motor local; chamada propositalmente inoperante (evita 422). */
async function syncParams(){ return; }
function renderKinds(){ const box=document.getElementById('kind-list'); box.innerHTML=''; KINDS.forEach(k=>{ const b=document.createElement('button'); b.className='kind-button'+(k===currentKind?' active':''); b.textContent=k; b.onclick=()=>switchKind(k); box.appendChild(b); }); }
async function switchKind(k){ currentKind=k; running=false; cancelAnimationFrame(raf); local=new LocalEngine(k,DEFAULTS[k]); renderKinds(); renderParams(); if(token)await ensureRemote(); loop(); }

/* ---------- main loop ---------- */
function loop(){ const tick=()=>{ if(running){ if(remote&&simId&&ws&&ws.readyState===1){ ws.send(JSON.stringify({dt:0.016,steps:2})); } else { local.step(0.016); local.step(0.016); renderState(local.getState()); } } raf=requestAnimationFrame(tick); }; cancelAnimationFrame(raf); raf=requestAnimationFrame(tick); }
setInterval(()=>{ if(!running){ renderState(local.getState()); } },500);

/* ---------- export / report / persistence ---------- */
function download(name,content,type){ const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([content],{type})); a.download=name; a.click(); }
function toCSV(st){ const rows=[['key','value']]; const flat=(o,pre='')=>{ for(const k in o){ const v=o[k]; if(Array.isArray(v))rows.push([pre+k,`len=${v.length}`]); else if(typeof v==='object'&&v)flat(v,pre+k+'.'); else rows.push([pre+k,String(v)]); } }; flat(st); return rows.map(r=>r.join(',')).join('\n'); }
async function doExport(){ const fmt=document.getElementById('export-fmt').value; if(remote&&simId&&token){ try{ const r=await fetch(`${API}/api/simulations/${simId}/export?format=${fmt}`,{headers:{Authorization:'Bearer '+token}}); if(r.ok){ const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`sim-${currentKind}.${fmt==='json'?'json':fmt==='csv'?'csv':'dat'}`; a.click(); return; } }catch(e){} } const st=local.getState(); download(`sim-${currentKind}.${fmt==='csv'?'csv':'json'}`, fmt==='csv'?toCSV(st):JSON.stringify({kind:currentKind,params:local.params,state:st},null,2), 'application/octet-stream'); }
function doReport(){ const st=local.getState(); const stats={kind:currentKind,t:local.t,step:st.step||0,params:local.params}; let txt=`COMPLEXSIM REPORT\nkind: ${currentKind}\nt: ${local.t.toFixed(2)}s\nparams: ${JSON.stringify(local.params)}\nstate keys: ${Object.keys(st).join(', ')}\n`; if(st.loss_history)txt+=`final loss: ${st.loss_history[st.loss_history.length-1]}\n`; if(st.S!==undefined)txt+=`SIR S=${st.S.toFixed(1)} I=${st.I.toFixed(1)} R=${st.R.toFixed(1)}\n`; document.getElementById('report-box').textContent=txt; if(st.loss_history)drawCurve(cctx,st.loss_history,'#e74c3c'); else if(st.history)drawBio(cctx,st.history); }

/* ---------- wiring ---------- */
document.getElementById('run-btn').onclick=()=>{running=true;};
document.getElementById('pause-btn').onclick=()=>{running=false;};
document.getElementById('step-btn').onclick=()=>{ local.step(0.016); renderState(local.getState()); };
document.getElementById('reset-btn').onclick=()=>{ local=new LocalEngine(currentKind,DEFAULTS[currentKind]); renderParams(); renderState(local.getState()); };
document.getElementById('export-btn').onclick=doExport;
document.getElementById('report-btn').onclick=doReport;
document.getElementById('save-btn').onclick=()=>{ localStorage.setItem('sim-'+currentKind,JSON.stringify({params:local.params,state:local.getState()})); download(`sim-${currentKind}-state.json`,JSON.stringify({kind:currentKind,params:local.params,state:local.getState()},null,2),'application/json'); };
document.getElementById('load-btn').onclick=()=>document.getElementById('load-file').click();
document.getElementById('load-file').onchange=e=>{ const f=e.target.files[0]; if(!f)return; const r=new FileReader(); r.onload=()=>{ try{ const d=JSON.parse(r.result); if(d.params)local.params=d.params; renderParams(); renderState(local.getState()); }catch(err){alert('invalid file');} }; r.readAsText(f); };
document.getElementById('login-btn').onclick=async()=>{ const u=document.getElementById('user-input').value||'admin', p=document.getElementById('pass-input').value||'admin'; try{ let r=await fetch(API+'/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})}).then(x=>x.json()).catch(()=>null); let d=await fetch(API+'/api/auth/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`username=${u}&password=${p}`}).then(x=>x.json()); token=d.access_token; document.getElementById('login-area').style.display='none'; document.getElementById('user-area').style.display='block'; document.getElementById('user-name').textContent=u; await ensureRemote(); }catch(e){ alert('backend offline — modo local'); } };
document.getElementById('logout-btn').onclick=()=>{ token=null; simId=null; remote=false; document.getElementById('login-area').style.display='block'; document.getElementById('user-area').style.display='none'; };
document.getElementById('theme-btn').onclick=()=>document.body.classList.toggle('dark');
/* API base setting (persistente) */
try {
  const sb = document.getElementById('status-box');
  const inp = document.createElement('input');
  inp.value = API; inp.title = 'API base URL'; inp.style.cssText = 'width:100%;margin-top:.4rem;padding:.4rem;font-size:.75rem';
  inp.onchange = () => { localStorage.setItem('sim-api', inp.value.replace(/\/$/, '')); location.reload(); };
  sb.appendChild(document.createElement('br')); sb.appendChild(inp);
} catch (e) {}
document.body.classList.add('dark');
renderKinds(); renderParams(); setLang(lang); loop(); renderState(local.getState());
