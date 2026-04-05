// ══════════════════════════════════════════════════════════════════════════
// KEYBOARD SHORTCUTS
// ══════════════════════════════════════════════════════════════════════════
function handleKey(e){
  if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT') return;
  switch(e.key){
    case '1': setBar(1); break;
    case '2': setBar(5); break;
    case '3': setBar(15); break;
    case '4': setBar(30); break;
    case '5': setBar(60); break;
    case 'e': case 'E': toggleInd('ema'); break;
    case 's': case 'S': toggleInd('sma'); break;
    case 'b': case 'B': toggleInd('bb'); break;
    case 'h': case 'H': setDraw('hline'); break;
    case 't': case 'T': setDraw('trend'); break;
    case 'f': case 'F': setDraw('fib'); break;
    case 'Escape': S.drawMode=null;S.drawClicks=[];document.querySelectorAll('.draw-mode').forEach(el=>el.style.display='none');document.querySelectorAll('#btnHLine,#btnTrend,#btnFib').forEach(b=>b.classList.remove('active'));break;
    case 'r': case 'R': combCandleChart?.timeScale().fitContent();fullCandleChart?.timeScale().fitContent();break;
    case 'c': case 'C': {const syms=['SPY','QQQ','AAPL','TSLA','NVDA','AMZN'];const i=(syms.indexOf(S.sym)+1)%syms.length;setSym(syms[i]);break;}
    // Nav shortcuts (Alt+number)
    case 'F1': e.preventDefault(); navTo('combined'); break;
    case 'F2': e.preventDefault(); navTo('flow'); break;
    case 'F3': e.preventDefault(); navTo('candles'); break;
    case 'F4': e.preventDefault(); navTo('options'); break;
    case 'F5': e.preventDefault(); navTo('agent'); switchAgentTab('positions'); break;
  }
}

