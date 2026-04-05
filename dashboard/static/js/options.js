// ══════════════════════════════════════════════════════════════════════════
// OPTIONS — expirations + chain
// ══════════════════════════════════════════════════════════════════════════
async function loadSidebarOptions(){
  // Fetch nearest expiration's snapshot to populate sidebar metrics (P/C, Max Pain, IV)
  try{
    const expR = await fetch(`/api/options/expirations?root=${S.sym}`);
    const expD = await expR.json();
    if(!expD.expirations || !expD.expirations.length) return;
    const nearestExp = expD.expirations[0]; // nearest expiration

    const [snapR, chainR] = await Promise.all([
      fetch(`/api/options/snapshot?root=${S.sym}&exp=${nearestExp}`),
      fetch(`/api/options/chain?root=${S.sym}&exp=${nearestExp}`),
    ]);
    const snap = await snapR.json();
    const chain = await chainR.json();

    // Update sidebar metrics
    if(snap.pc_ratio != null){
      document.getElementById('mPcr').textContent = snap.pc_ratio.toFixed(2);
    }
    if(snap.max_pain){
      document.getElementById('mMaxPain').textContent = '$'+parseFloat(snap.max_pain).toFixed(0);
    }
    // IV from ATM options
    const allContracts = [...(chain.calls||[]), ...(chain.puts||[])];
    const atmIv = allContracts.filter(c => S.lastPrice && Math.abs(c.strike - S.lastPrice) < 5 && c.iv != null).map(c => c.iv);
    if(atmIv.length){
      const avgIv = (atmIv.reduce((a,b)=>a+b,0) / atmIv.length * 100).toFixed(1);
      document.getElementById('mIv').textContent = avgIv + '%';
    }
  }catch(e){ console.debug('Sidebar options load:', e); }
}

async function loadExpirations(){
  try{
    const r = await fetch(`/api/options/expirations?root=${S.sym}`);
    const d = await r.json();
    if(d.expirations && d.expirations.length){
      const exps = d.expirations.slice(0,12);
      // Populate expiration selector on options board
      const sel = document.getElementById('selExpBoard');
      if(sel){
        sel.innerHTML = exps.map(e => `<option value="${e}">${e}</option>`).join('');
      }
      // Auto-load if on options tab
      if(S.activeTab === 'options') loadOptionsBoard();
    } else if(d.error){
      console.debug('Expirations:', d.error);
    }
  }catch(e){console.error('Expirations failed:', e);}
}

async function loadOptionsBoard(){
  const exp = document.getElementById('selExpBoard')?.value;
  if(!exp) return;
  const grid = document.getElementById('optBoardGrid');
  if(!grid) return;
  grid.innerHTML = UI.loading('Loading options board...');

  try{
    const [chainR, snapR] = await Promise.all([
      fetch(`/api/options/chain?root=${S.sym}&exp=${exp}`),
      fetch(`/api/options/snapshot?root=${S.sym}&exp=${exp}`),
    ]);
    const chain = await chainR.json();
    const snap = await snapR.json();

    if(chain.error && !chain.calls?.length && !chain.puts?.length){
      grid.innerHTML=UI.empty(chain.error);
      return;
    }

    // Update board stats
    const pcr = snap.pc_ratio?.toFixed(2) || '--';
    const mp = snap.max_pain ? '$'+parseFloat(snap.max_pain).toFixed(0) : '--';
    document.getElementById('obPcr').textContent = pcr;
    document.getElementById('obMaxPain').textContent = mp;
    document.getElementById('obCallVol').textContent = (snap.call_volume||0).toLocaleString();
    document.getElementById('obPutVol').textContent = (snap.put_volume||0).toLocaleString();
    document.getElementById('obSrc').textContent = chain.source || '--';

    // Update sidebar metrics
    document.getElementById('mPcr').textContent = pcr;
    document.getElementById('mMaxPain').textContent = mp;
    // IV from ATM options (only available when ThetaData enriches the chain)
    const calls = chain.calls||[], puts = chain.puts||[];
    const allContracts = [...calls, ...puts];
    const atmIv = allContracts.filter(c => S.lastPrice && Math.abs(c.strike - S.lastPrice) < 3 && c.iv != null).map(c => c.iv);
    if(atmIv.length){
      const avgIv = (atmIv.reduce((a,b)=>a+b,0) / atmIv.length * 100).toFixed(1);
      document.getElementById('mIv').textContent = avgIv + '%';
    } else {
      document.getElementById('mIv').textContent = '--';
    }

    const strikes = [...new Set([...calls.map(c=>c.strike),...puts.map(p=>p.strike)])].sort((a,b)=>a-b);

    // Filter by strike range
    const nStrikes = parseInt(document.getElementById('selStrikes')?.value || 20);
    let visible = strikes;
    if(nStrikes < 999 && S.lastPrice){
      const atm = S.lastPrice;
      const nearIdx = strikes.reduce((best,s,i) => Math.abs(s-atm)<Math.abs(strikes[best]-atm)?i:best, 0);
      const lo = Math.max(0, nearIdx - nStrikes);
      const hi = Math.min(strikes.length, nearIdx + nStrikes);
      visible = strikes.slice(lo, hi);
    }

    const callMap = {}, putMap = {};
    calls.forEach(c => callMap[c.strike] = c);
    puts.forEach(p => putMap[p.strike] = p);

    // Detect if we have greeks data (from ThetaData enrichment)
    const hasGreeks = [...calls,...puts].some(c => c.delta != null || c.iv != null);

    // Full options board table — CSS classes from opt-table system
    let html = `<table class="opt-table">
      <thead>
        <tr>
          <th colspan="${hasGreeks?7:5}" class="opt-hdr-group calls">CALLS</th>
          <th class="opt-hdr-group">STRIKE</th>
          <th colspan="${hasGreeks?7:5}" class="opt-hdr-group puts">PUTS</th>
        </tr>
        <tr>
          <th class="opt-col-hdr">Bid</th><th class="opt-col-hdr">Ask</th><th class="opt-col-hdr">Last</th>
          <th class="opt-col-hdr">Vol</th><th class="opt-col-hdr">OI</th>
          ${hasGreeks?'<th class="opt-col-hdr">IV</th><th class="opt-col-hdr">\u0394</th>':''}
          <th class="opt-col-hdr opt-strike"></th>
          ${hasGreeks?'<th class="opt-col-hdr">\u0394</th><th class="opt-col-hdr">IV</th>':''}
          <th class="opt-col-hdr">OI</th><th class="opt-col-hdr">Vol</th>
          <th class="opt-col-hdr">Last</th><th class="opt-col-hdr">Ask</th><th class="opt-col-hdr">Bid</th>
        </tr>
      </thead><tbody>`;

    visible.forEach(s => {
      const c = callMap[s]||{}, p = putMap[s]||{};
      const isAtm = S.lastPrice && Math.abs(s - S.lastPrice) < 2;
      const rowCls = isAtm ? ' class="opt-atm"' : '';
      const fmt = (v,d=2) => v ? v.toFixed(d) : '-';
      html += `<tr${rowCls}>
        <td class="opt-bid">${fmt(c.bid)}</td>
        <td class="opt-ask">${fmt(c.ask)}</td>
        <td>${fmt(c.last||c.mid)}</td>
        <td class="opt-vol-call">${c.volume||'-'}</td>
        <td class="opt-oi">${c.open_interest||'-'}</td>
        ${hasGreeks?`<td>${c.iv?(c.iv*100).toFixed(1)+'%':'-'}</td>
        <td>${c.delta!=null?c.delta.toFixed(3):'-'}</td>`:''}
        <td class="opt-strike">${s.toFixed(1)}</td>
        ${hasGreeks?`<td>${p.delta!=null?p.delta.toFixed(3):'-'}</td>
        <td>${p.iv?(p.iv*100).toFixed(1)+'%':'-'}</td>`:''}
        <td class="opt-oi">${p.open_interest||'-'}</td>
        <td class="opt-vol-put">${p.volume||'-'}</td>
        <td>${fmt(p.last||p.mid)}</td>
        <td class="opt-ask">${fmt(p.ask)}</td>
        <td class="opt-bid">${fmt(p.bid)}</td>
      </tr>`;
    });

    html += '</tbody></table>';
    grid.innerHTML = html;

    // Enhance options board table with resizable columns
    const obTable = grid.querySelector('table');
    if(obTable && typeof TableUpgrade !== 'undefined'){
      TableUpgrade.enhance(obTable, { resizable: true, sortable: false, persistKey: 'optBoard' });
    }

  }catch(e){
    grid.innerHTML = UI.empty('Error: ' + e.message);
  }
}

