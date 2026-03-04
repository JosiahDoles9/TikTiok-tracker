const app = document.getElementById('app');
let currentSyncId = null;

async function api(path, opts={}) {
  const r = await fetch(path, {headers:{'content-type':'application/json'}, ...opts});
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function fmt(n){ return Number(n||0).toLocaleString(); }

async function loadDashboard(){
  const d = await api('/api/dashboard');
  app.innerHTML = `
  <div class="grid">
    <div class="card">Total products<br><b>${d.totalProducts}</b></div>
    <div class="card">Total metric<br><b>${fmt(d.totalMetric)}</b></div>
    <div class="card">Last sync<br><b>${d.lastSync?.status || 'none'}</b><br>${d.lastSync?.started_at || ''}</div>
  </div>
  <div class="card"><h3>Top categories</h3>${d.categories.map(c=>`${c.category}: ${fmt(c.m)}`).join('<br>')}</div>
  <div class="card"><h3>Best sellers</h3><ol>${d.bestSellers.map(p=>`<li>${p.name} (${p.category})</li>`).join('')}</ol></div>`;
}

async function loadTrending(){
  const cats = await api('/api/categories');
  const data = await Promise.all(cats.map(c=>api('/api/trending?category='+encodeURIComponent(c)).then(v=>({c,v}))));
  app.innerHTML = data.map(({c,v})=>`<div class="card"><h3>${c}</h3>${v.length===0?'No data':v.map(p=>`
    <div><b>#${p.rank} ${p.name}</b> <small>${p.metric_name}: ${fmt(p.metric_value)}</small>
    <a href="${p.product_url}" target="_blank" rel="noopener">Open product</a></div>`).join('')}</div>`).join('');
}

async function loadProducts(){
  app.innerHTML = `<div class='card'>
    <input id='search' placeholder='Search products'/> <button id='go'>Search</button>
    <div id='results'></div>
  </div>`;
  async function run(){
    const q = document.getElementById('search').value;
    const rows = await api('/api/products?sort=metric&search='+encodeURIComponent(q));
    const html = `<table><tr><th>Name</th><th>Category</th><th>Rank</th><th>Link</th></tr>${rows.map(r=>`<tr><td><a href='#' data-id='${r.id}' class='detail'>${r.name}</a></td><td>${r.category}</td><td>${r.rank ?? ''}</td><td><a href='${r.product_url}' target='_blank'>Open</a></td></tr>`).join('')}</table><div id='detail'></div>`;
    document.getElementById('results').innerHTML = html;
    document.querySelectorAll('.detail').forEach(el=>el.onclick=async(e)=>{e.preventDefault();const id=el.dataset.id;const d=await api('/api/products/'+id);document.getElementById('detail').innerHTML=`<div class='card'><h4>${d.name}</h4>${d.topVideos.map(v=>`<div class='video'><a target='_blank' href='${v.video_url}'>Video link</a><br>${v.ai_why_it_did_well}</div>`).join('')}</div>`});
  }
  document.getElementById('go').onclick = run;
  run();
}

async function loadAnalytics(){
  const d = await api('/api/dashboard');
  app.innerHTML = `<div class='card'><h3>Category ranking</h3>${d.categories.map((c,i)=>`${i+1}. ${c.category} — ${fmt(c.m)}`).join('<br>')}</div>
  <div class='card'><h3>Since last sync</h3>Products: ${d.totalProducts}</div>`;
}

async function loadTikTok(){
  let accounts = [];
  let best = [];
  let videos = [];
  try { accounts = await api('/api/integrations/tiktok/accounts'); } catch { accounts = []; }
  try { best = await api('/api/integrations/tiktok/best-performing?limit=15'); } catch { best = []; }
  try { videos = await api('/api/integrations/tiktok/videos'); } catch { videos = []; }

  app.innerHTML = `<div class='card'>
    <h3>TikTok Display API</h3>
    <button id='connectTk'>Connect TikTok</button>
    <div id='tkAccounts'>${accounts.length?accounts.map(a=>`<div>${a.display_name || a.open_id} <button class='syncTk' data-id='${a.id}'>Sync</button></div>`).join(''):'No connected accounts yet'}</div>
  </div>
  <div class='card'><h3>Best Performing Videos</h3>${best.length?best.map(v=>`<div><a target='_blank' href='${v.embed_link || v.share_url || '#'}'>${v.title || v.video_id}</a> · views ${fmt(v.view_count)} · likes ${fmt(v.like_count)}</div>`).join(''):'No video metrics yet'}</div>
  <div class='card'><h3>Recent Video Library</h3>${videos.length?videos.slice(0,50).map(v=>`<div>${v.title || v.video_id} · ${v.create_time || ''} · <a target='_blank' href='${v.embed_link || v.share_url || '#'}'>Open</a></div>`).join(''):'No videos synced yet'}</div>`;

  document.getElementById('connectTk').onclick = async ()=>{
    const res = await api('/api/integrations/tiktok/connect');
    window.location.href = res.authorizationUrl;
  };
  document.querySelectorAll('.syncTk').forEach(btn=>btn.onclick=async()=>{
    const id = btn.dataset.id;
    await api('/api/integrations/tiktok/sync',{method:'POST', body: JSON.stringify({accountId:id})});
    alert('TikTok sync started/completed. Reloading...');
    loadTikTok();
  });
}

async function monitorSync(){
  if(!currentSyncId) return;
  const s = await api('/api/sync/'+currentSyncId);
  document.getElementById('syncStatus').textContent = `${s.status} ${s.progressPercent}% ${s.currentCategory||''}`;
  if(s.status==='running'){ setTimeout(monitorSync, 1500); }
  else { currentSyncId = null; loadDashboard(); }
}

async function startSync(){
  const {syncId} = await api('/api/sync', {method:'POST'});
  currentSyncId = syncId;
  monitorSync();
}

document.getElementById('syncBtn').onclick = startSync;
document.querySelectorAll('nav button').forEach(btn=>btn.onclick=()=>({dashboard:loadDashboard,trending:loadTrending,products:loadProducts,analytics:loadAnalytics,tiktok:loadTikTok}[btn.dataset.page]()));
loadDashboard();
