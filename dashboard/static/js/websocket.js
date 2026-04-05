// ══════════════════════════════════════════════════════════════════════════
// WEBSOCKET — Engine ticks + signals
// ══════════════════════════════════════════════════════════════════════════
function connectWS(){
  const url = `ws://${location.hostname}:8081/ws`;
  try{ S.ws = new WebSocket(url); }catch(e){ return; }

  S.ws.onopen = () => {
    S.connected = true;
    S._engineRetryMs = 3000;
    S._engineRetries = 0; // Reset backoff + retries on successful connect
    document.getElementById('dotEng').className = 'dot on';
    const lblEng = document.getElementById('lblEng');
    if(lblEng){ lblEng.textContent = 'Connected'; lblEng.style.color = 'var(--grn)'; }
    // Don't stop REST polling yet — verify engine is actually delivering ticks.
    // If no ticks arrive within 10s, the engine has stale data → fallback to REST.
    if(S._staleCheckTimer) clearTimeout(S._staleCheckTimer);
    S._staleCheckTimer = setTimeout(() => {
      if(S.ticks === 0 && S.connected){
        console.warn('Engine WS connected but 0 ticks after 10s — engine data is stale. Starting REST polling fallback.');
        startRestPolling();
      }
    }, 10000);
    // Fetch engine stats to display data source
    fetchEngineStats();
  };

  S.ws.onmessage = (evt) => {
    try{
      const ev = JSON.parse(evt.data);
      handleEvent(ev);
    }catch(e){}
  };

  S.ws.onclose = () => {
    S.connected = false;
    document.getElementById('dotEng').className = 'dot off';
    const lblEngOff = document.getElementById('lblEng');
    if(lblEngOff){ lblEngOff.textContent = 'Disconnected'; lblEngOff.style.color = 'var(--dim)'; }
    // Exponential backoff: 3s → 6s → 12s → … max 60s, stop after 10 attempts
    S._engineRetries = (S._engineRetries || 0) + 1;
    if(S._engineRetries > 10){
      console.warn('Engine WS: gave up after 10 retries. Restart flow engine and reload page.');
      return;
    }
    S._engineRetryMs = Math.min((S._engineRetryMs || 3000) * 2, 60000);
    setTimeout(connectWS, S._engineRetryMs);
  };

  S.ws.onerror = () => {};
}

async function fetchEngineStats(){
  try{
    const r = await fetch(`http://${location.hostname}:8081/stats`);
    const d = await r.json();
    if(d.data_source){
      document.getElementById('lblData').textContent = d.data_source;
    }
    if(d.ticks_processed > 0){
      document.getElementById('dotData').className = 'dot on';
    }
  }catch(e){}
}

function handleEvent(ev){
  const t = ev.type || ev.event_type;

  if(t === 'Tick' || t === 'tick'){
    S.ticks++;
    // Engine is delivering real ticks — cancel stale check & stop REST fallback
    if(S._staleCheckTimer){ clearTimeout(S._staleCheckTimer); S._staleCheckTimer = null; }
    if(S.ticks === 1) stopRestPolling();
    const price = ev.price;
    const size = ev.size || 1;
    const side = (ev.side || '').toLowerCase();
    // Use the tick's original timestamp from the engine (UTC ISO string)
    const tickTs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
    if(price){
      S.lastPrice = price;
      updatePrice(price, S.prevClose);

      // Feed into real-time order flow with original timestamp
      handleFlowTick(price, size, side === 'buy' || side === 'sell' ? side : null, tickTs);

      // Build live 1-min candle
      const now = Math.floor(Date.now()/1000);
      const barTime = now - (now % S.liveInterval);
      let candle = S.liveCandles.get(barTime);
      if(!candle){
        candle = {open:price,high:price,low:price,close:price,volume:0};
        S.liveCandles.set(barTime, candle);
      }
      candle.high = Math.max(candle.high, price);
      candle.low = Math.min(candle.low, price);
      candle.close = price;
      candle.volume += size;

      if(S.tf === 'live'){
        const arr = [...S.liveCandles.entries()].sort((a,b)=>a[0]-b[0]).map(([t,c])=>({time:t,...c}));
        try{ combCandleS.setData(arr); }catch(e){}
        try{ fullCandleS.setData(arr); }catch(e){}
      }
    }
  }
  else if(t === 'Signal' || t === 'signal'){
    addSignal(ev);
  }
  else if(t === 'Heartbeat' || t === 'heartbeat'){
    if(ev.last_price && ev.last_price > 0){
      S.lastPrice = ev.last_price;
      updatePrice(ev.last_price, S.prevClose);
    }
    if(ev.ticks_processed > 0){
      document.getElementById('dotData').className = 'dot on';
    }
    if(ev.data_source){
      document.getElementById('lblData').textContent = ev.data_source;
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════
// DASHBOARD WS — SIP stream via Python backend (port 8000)
// Receives: trades, quotes, bars, LULD, halts, trade corrections
// ══════════════════════════════════════════════════════════════════════════
let dashWs = null;
let luldData = {up:[], down:[]};  // LULD band history for chart
let haltActive = false;

// ── Stream-awareness tracking ──
// Tracks whether the dashboard WS is actively receiving trade/quote data,
// so we can suppress redundant REST polling when the stream is live.
var _streamState = {
  connected: false,
  lastTradeMs: 0,
  lastQuoteMs: 0,
  tradeCount: 0,
  quoteCount: 0,
  // Consider stream "active" if we received data within this window
  freshnessMs: 8000,
};
function isStreamActive(){
  return _streamState.connected && (Date.now() - _streamState.lastTradeMs) < _streamState.freshnessMs;
}
function isQuoteStreamActive(){
  return _streamState.connected && (Date.now() - _streamState.lastQuoteMs) < _streamState.freshnessMs;
}

function connectDashboardWS(){
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws`;
  try{ dashWs = new WebSocket(url); }catch(e){ return; }

  dashWs.onopen = () => {
    _streamState.connected = true;
    _streamState._retryMs = 3000;
    _streamState._retries = 0;
    console.log('Dashboard WS connected (Alpaca stream relay)');
  };

  dashWs.onmessage = (evt) => {
    try{
      const ev = JSON.parse(evt.data);
      handleStreamEvent(ev);
    }catch(e){}
  };

  dashWs.onclose = () => {
    _streamState.connected = false;
    _streamState._retries = (_streamState._retries || 0) + 1;
    if(_streamState._retries > 10){
      console.warn('Dashboard WS: gave up after 10 retries.');
      return;
    }
    _streamState._retryMs = Math.min((_streamState._retryMs || 3000) * 2, 60000);
    setTimeout(connectDashboardWS, _streamState._retryMs);
  };

  dashWs.onerror = () => {};
}

function handleStreamEvent(ev){
  const t = ev.type;

  if(t === 'trade'){
    // Track stream freshness for smart polling
    _streamState.lastTradeMs = Date.now();
    _streamState.tradeCount++;
    // Stop REST polling once WS is delivering ticks
    if(_streamState.tradeCount === 1 && restPollTimer) stopRestPolling();

    // Real-time trade from SIP stream — update price + feed order flow
    if(ev.symbol === S.sym && ev.price){
      S.lastPrice = ev.price;
      updatePrice(ev.price, S.prevClose);
      // Feed into order flow with NBBO-classified side
      const side = ev.side || null;
      const tickTs = ev.timestamp ? new Date(ev.timestamp).getTime() : Date.now();
      handleFlowTick(ev.price, ev.size || 1, side, tickTs);

      // Build live candle + cap Map size to prevent memory bloat
      const now = Math.floor(Date.now()/1000);
      const barTime = now - (now % S.liveInterval);
      let candle = S.liveCandles.get(barTime);
      if(!candle){
        candle = {open:ev.price,high:ev.price,low:ev.price,close:ev.price,volume:0};
        S.liveCandles.set(barTime, candle);
        // Cap at 500 candles to prevent memory leak during long sessions
        if(S.liveCandles.size > 500){
          const oldest = S.liveCandles.keys().next().value;
          S.liveCandles.delete(oldest);
        }
      }
      candle.high = Math.max(candle.high, ev.price);
      candle.low = Math.min(candle.low, ev.price);
      candle.close = ev.price;
      candle.volume += ev.size || 1;
    }
  }
  else if(t === 'quote'){
    _streamState.lastQuoteMs = Date.now();
    _streamState.quoteCount++;
    // NBBO update — update bid/ask display
    if(ev.symbol === S.sym && ev.bid && ev.ask && ev.bid > 0 && ev.ask > 0){
      const spread = (ev.ask - ev.bid).toFixed(2);
      document.getElementById('hBidAsk').textContent = `${ev.bid.toFixed(2)} × ${ev.ask.toFixed(2)} (${spread})`;
    }
  }
  else if(t === 'bar'){
    // Completed minute bar from Alpaca — append to chart if matching timeframe
    if(ev.symbol === S.sym && S.tf === '1Min'){
      try{
        const ts = ev.timestamp ? Math.floor(new Date(ev.timestamp).getTime()/1000) : Math.floor(Date.now()/1000);
        const barTime = ts - (ts % 60);
        const bar = {time:barTime, open:ev.open, high:ev.high, low:ev.low, close:ev.close};
        const vol = {time:barTime, value:ev.volume, color: ev.close>=ev.open ? 'rgba(38,166,154,.4)' : 'rgba(239,83,80,.4)'};
        fullCandleS.update(bar);
        fullVolS.update(vol);
        combCandleS.update(bar);
        combVolS.update(vol);   // Was missing — combined tab volumes now update
        // Sync rtCandle so updateRealtimeCandle doesn't conflict
        rtCandle = {time:barTime, open:ev.open, high:ev.high, low:ev.low, close:ev.close, volume:ev.volume||0};
      }catch(e){}
    }
  }
  else if(t === 'bar_update'){
    // Corrected bar — update existing bar on BOTH charts
    if(ev.symbol === S.sym){
      try{
        const ts = ev.timestamp ? Math.floor(new Date(ev.timestamp).getTime()/1000) : 0;
        if(ts > 0){
          const barTime = ts - (ts % 60);
          const bar = {time:barTime, open:ev.open, high:ev.high, low:ev.low, close:ev.close};
          fullCandleS.update(bar);
          combCandleS.update(bar);
        }
      }catch(e){}
    }
  }
  else if(t === 'luld'){
    // Limit Up / Limit Down bands — plot on chart
    if(ev.symbol === S.sym){
      const ts = ev.timestamp ? Math.floor(new Date(ev.timestamp).getTime()/1000) : Math.floor(Date.now()/1000);
      if(ev.limit_up > 0) luldData.up.push({time:ts, value:ev.limit_up});
      if(ev.limit_down > 0) luldData.down.push({time:ts, value:ev.limit_down});
      // Cap arrays to prevent memory bloat (keep last 500 LULD events)
      if(luldData.up.length > 500) luldData.up = luldData.up.slice(-500);
      if(luldData.down.length > 500) luldData.down = luldData.down.slice(-500);
      try{
        if(luldData.up.length) fullLuldUpS.setData(luldData.up);
        if(luldData.down.length) fullLuldDownS.setData(luldData.down);
      }catch(e){}
    }
  }
  else if(t === 'trading_status'){
    // Trading halt/resume
    if(ev.symbol === S.sym){
      const isHalt = ev.status_code === 'H' || ev.status_code === 'T';
      haltActive = isHalt;
      const haltBanner = document.getElementById('haltBanner');
      if(haltBanner){
        isHalt ? haltBanner.classList.remove('u-hidden') : haltBanner.classList.add('u-hidden');
        haltBanner.textContent = isHalt
          ? `⚠ TRADING HALTED — ${ev.reason_message || ev.status_message || 'Regulatory halt'}`
          : '';
      }
      // Add to signals feed
      addFlowSignal({
        type: isHalt ? 'halt' : 'resume',
        severity: 'critical',
        text: isHalt ? `HALT: ${ev.reason_message || 'Trading halted'}` : 'Trading resumed',
        time: new Date().toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'}),
      });
    }
  }
  else if(t === 'stream_status'){
    // Alpaca stream connection status
    if(ev.status === 'connected'){
      document.getElementById('dotData').className = 'dot on';
      document.getElementById('lblData').textContent = ev.data_source || 'LIVE WS';
      const lblDS = document.getElementById('lblDataStatus');
      if(lblDS){ lblDS.textContent = 'Connected'; lblDS.style.color = 'var(--grn)'; }
      // Stop REST polling since we have WebSocket streaming now
      stopRestPolling();
    } else if(ev.status === 'proxy_blocked'){
      // Network proxy blocks WS — REST polling is the fallback
      document.getElementById('dotData').className = 'dot dim';
      document.getElementById('lblData').textContent = 'REST polling (WS blocked)';
      const lblDS2 = document.getElementById('lblDataStatus');
      if(lblDS2){ lblDS2.textContent = 'Degraded'; lblDS2.style.color = 'var(--ylw)'; }
      console.warn('Alpaca WS blocked by proxy — using REST polling for price updates');
    } else if(ev.status === 'disconnected'){
      document.getElementById('dotData').className = 'dot dim';
      const lblDS3 = document.getElementById('lblDataStatus');
      if(lblDS3){ lblDS3.textContent = 'Disconnected'; lblDS3.style.color = 'var(--dim)'; }
    }
  }
  else if(t === 'trade_correction' || t === 'trade_cancel'){
    // Log but don't alert user for every correction
    console.log(`Trade ${t}: ${ev.symbol}`, ev);
  }
}

function addSignal(ev){
  // This is called for engine signals. Note: AI signals use renderAISignalCard() instead.
  // Do NOT rebuild the entire sigFeed (that would destroy AI signal cards)
  // Simply ignore engine signals if they would conflict with AI signals display
  // Engine signals are low priority compared to AI signals
  // Commented out the old code that would overwrite sigFeed HTML:
  /*
  const side = (ev.direction || ev.side || '').toLowerCase();
  const sig = {
    side: side.includes('buy') ? 'buy' : side.includes('sell') ? 'sell' : 'neutral',
    strike: ev.strike || ev.detail || '',
    conf: ev.confidence || 0,
    reason: ev.reason || ev.detail || '',
    time: new Date().toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'}),
  };
  S.signals.unshift(sig);
  if(S.signals.length > S.maxSignals) S.signals.pop();

  const feed = document.getElementById('sigFeed');
  feed.innerHTML = S.signals.map(s => `
    <div class="sig ${s.side}">
      <div class="sig-hdr">
        <span class="sig-type ${s.side}">${s.side.toUpperCase()}</span>
        <span style="font-size:9px;font-weight:600">${s.strike}</span>
        ${s.conf ? `<span class="sig-conf" style="color:${s.conf>80?'var(--grn)':s.conf>60?'var(--ylw)':'var(--red)'}">${s.conf}%</span>` : ''}
        <span class="sig-time">${s.time}</span>
      </div>
      <div class="sig-detail">${s.reason}</div>
    </div>
  `).join('');
  */
  // Engine signals are now ignored in favor of AI signals from pollAISignal()
}

