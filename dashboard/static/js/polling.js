// ══════════════════════════════════════════════════════════════════════════
// PERIODIC REFRESH
// ══════════════════════════════════════════════════════════════════════════
function refreshLiveData(){
  const session = getMarketSession();
  const wsTradesActive = isStreamActive();
  const wsQuotesActive = isQuoteStreamActive();

  // ── Price fetch: SKIP if WS trade stream is delivering fresh data ──
  if(!wsTradesActive){
    fetch(`/api/market?symbol=${S.sym}`).then(r=>r.json()).then(d=>{
      if(d.spy){
        let displayPrice = d.spy.price;
        if(session !== 'regular' && d.spy.bid && d.spy.ask && d.spy.bid > 0 && d.spy.ask > 0){
          const mid = (d.spy.bid + d.spy.ask) / 2;
          if(Math.abs(mid - d.spy.price) > 0.01) displayPrice = Math.round(mid * 100) / 100;
        }
        S.lastPrice = displayPrice;
        S.prevClose = d.spy.prev_close || d.spy.price;
        updatePrice(displayPrice, S.prevClose);
        if(d.spy.bid && d.spy.ask){
          const spread = (d.spy.ask - d.spy.bid).toFixed(2);
          document.getElementById('hBidAsk').textContent = `${d.spy.bid.toFixed(2)} × ${d.spy.ask.toFixed(2)} (${spread})`;
          document.getElementById('dotData').className = session === 'closed' ? 'dot dim' : 'dot on';
        }
        const info = document.getElementById('dataSourceInfo');
        if(info) info.textContent = `${S.sym} via ${d.spy.source || 'Alpaca'}`;
      }
    }).catch(()=>{});
  }

  // ── Data label: reflect the active source ──
  if(wsTradesActive){
    const tps = _streamState.tradeCount > 10 ? Math.round(_streamState.tradeCount / ((Date.now() - _streamState.lastTradeMs + 1) / 1000)) : '';
    document.getElementById('lblData').textContent = `LIVE WS — SIP (${_streamState.tradeCount.toLocaleString()} ticks)`;
    document.getElementById('dotData').className = 'dot on';
  } else if(!S.connected){
    const sessionLabels = {'regular':'LIVE — SIP', 'pre-market':'Pre-Market', 'after-hours':'After Hours', 'closed':'Market Closed'};
    document.getElementById('lblData').textContent = sessionLabels[session] || 'SIP';
  }

  // ── Engine status: always check (lightweight) ──
  fetch('/api/status').then(r=>r.json()).then(d=>{
    const engDot = document.getElementById('dotEng');
    engDot.className = d.running ? 'dot on' : 'dot off';
    if(d.running && S.connected && d.data_source && d.data_source !== 'disconnected'){
      document.getElementById('lblData').textContent = `LIVE — ${d.data_source}`;
      document.getElementById('dotData').className = 'dot on';
    }
  }).catch(()=>{ document.getElementById('dotEng').className='dot off'; });

  // ── Quote fetch: SKIP if WS quote stream is delivering fresh NBBO ──
  if(!wsQuotesActive){
    fetch(`/api/quote?symbol=${S.sym}&feed=sip`).then(r=>r.json()).then(d=>{
      if(d.bid && d.ask){
        const spread = (d.ask - d.bid).toFixed(2);
        document.getElementById('hBidAsk').textContent = `${d.bid.toFixed(2)} × ${d.ask.toFixed(2)} (${spread})`;
      }
    }).catch(()=>{});
  }

  // ── Sidebar metrics from flow data ──
  if(S.flowData && S.flowData.meta){
    const meta = S.flowData.meta;
    if(meta.price_range && meta.price_range[0] && meta.price_range[1]){
      const vwap = ((meta.price_range[0] + meta.price_range[1]) / 2).toFixed(2);
      document.getElementById('mVwap').textContent = '$' + vwap;
    }
  }
}

