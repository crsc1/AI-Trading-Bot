/** Chart theme constants matching our design tokens (see DESIGN.md) */
export const chartTheme = {
  background: '#0a0a12',
  textColor: '#b0b0c8',
  fontFamily: "'Geist Mono', 'SF Mono', 'Menlo', monospace",
  gridColor: 'rgba(255,255,255,0.08)',

  upColor: '#00C805',
  downColor: '#FF5000',
  upWickColor: '#00C805',
  downWickColor: '#FF5000',

  // Extended hours: dimmed candles
  extUpColor: 'rgba(0,200,5,0.35)',
  extDownColor: 'rgba(255,80,0,0.35)',
  extUpWickColor: 'rgba(0,200,5,0.35)',
  extDownWickColor: 'rgba(255,80,0,0.35)',

  volumeUp: 'rgba(0,200,5,0.25)',
  volumeDown: 'rgba(255,80,0,0.25)',
  extVolumeUp: 'rgba(0,200,5,0.10)',
  extVolumeDown: 'rgba(255,80,0,0.10)',

  // Session boundary lines
  sessionLineColor: 'rgba(255,255,255,0.12)',

  crosshairColor: 'rgba(255,255,255,0.15)',
};

/** Indicator colors */
export const indicatorColors = {
  ema9: '#ffb300',
  ema21: '#ff7043',
  sma50: '#42a5f5',
  sma200: '#ab47bc',
  vwap: '#00e5ff',
  bbUpper: '#42a5f5',
  bbLower: '#42a5f5',
  bbMiddle: 'rgba(66,165,245,0.5)',
  rsi: '#ab47bc',
  macdLine: '#42a5f5',
  macdSignal: '#ff7043',
  macdHist: '#00C805',
  atr: '#26a69a',
  stochK: '#ef5350',
  stochD: '#42a5f5',
};
