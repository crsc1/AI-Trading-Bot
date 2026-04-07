import { type Component, createEffect, createSignal, createMemo, on } from 'solid-js';
import { TimeChart } from '@dschz/solid-lightweight-charts';
import type { ISeriesApi, Time, CandlestickData, HistogramData, LineData } from 'lightweight-charts';
import { market } from '../../signals/market';
import { chartTheme, indicatorColors } from '../../lib/theme';
import { calcEMA, calcSMA, calcBB, calcRSI, calcVWAP } from '../../lib/indicators';
import type { Candle } from '../../types/market';
import { ChartControls } from './ChartControls';

// Convert our candles to LWC candlestick format
function toCandlestickData(candles: Candle[]): CandlestickData<Time>[] {
  return candles.map((c) => ({
    time: c.time as Time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

// Convert our candles to LWC volume histogram format
function toVolumeData(candles: Candle[]): HistogramData<Time>[] {
  return candles.map((c) => ({
    time: c.time as Time,
    value: c.volume,
    color: c.close >= c.open ? chartTheme.volumeUp : chartTheme.volumeDown,
  }));
}

// Convert indicator data to LWC line format
function toLineData(data: { time: number; value: number }[]): LineData<Time>[] {
  return data.map((d) => ({ time: d.time as Time, value: d.value }));
}

export const CandleChart: Component = () => {
  let candleSeries: ISeriesApi<'Candlestick'> | undefined;
  let volumeSeries: ISeriesApi<'Histogram'> | undefined;

  // Which indicators are enabled
  const [indicators, setIndicators] = createSignal<Set<string>>(
    new Set(['ema9', 'ema21', 'vwap'])
  );

  const toggleIndicator = (id: string) => {
    setIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Compute indicator data from candles
  const candleData = createMemo(() => toCandlestickData(market.candles));
  const volumeData = createMemo(() => toVolumeData(market.candles));

  const ema9Data = createMemo(() => (indicators().has('ema9') ? toLineData(calcEMA(market.candles, 9)) : []));
  const ema21Data = createMemo(() => (indicators().has('ema21') ? toLineData(calcEMA(market.candles, 21)) : []));
  const sma50Data = createMemo(() => (indicators().has('sma50') ? toLineData(calcSMA(market.candles, 50)) : []));
  const vwapData = createMemo(() => (indicators().has('vwap') ? toLineData(calcVWAP(market.candles)) : []));
  const bbData = createMemo(() => {
    if (!indicators().has('bb')) return { upper: [], lower: [] };
    const bb = calcBB(market.candles, 20, 2);
    return { upper: toLineData(bb.upper), lower: toLineData(bb.lower) };
  });
  const rsiData = createMemo(() => (indicators().has('rsi') ? toLineData(calcRSI(market.candles, 14)) : []));

  // Update current candle in real-time
  createEffect(
    on(
      () => market.currentCandle,
      (candle) => {
        if (!candle || !candleSeries) return;
        candleSeries.update({
          time: candle.time as Time,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        });
        if (volumeSeries) {
          volumeSeries.update({
            time: candle.time as Time,
            value: candle.volume,
            color: candle.close >= candle.open ? chartTheme.volumeUp : chartTheme.volumeDown,
          });
        }
      }
    )
  );

  return (
    <div class="flex flex-col h-full min-h-0">
      <ChartControls indicators={indicators()} onToggle={toggleIndicator} />

      <div class="flex-1 min-h-0 relative overflow-hidden">
        <TimeChart
          autoSize
          layout={{
            background: { color: chartTheme.background },
            textColor: chartTheme.textColor,
            fontFamily: "'SF Mono', 'Menlo', 'Consolas', monospace",
            fontSize: 10,
          }}
          grid={{
            vertLines: { color: chartTheme.gridColor },
            horzLines: { color: chartTheme.gridColor },
          }}
          crosshair={{
            mode: 0, // Normal
            vertLine: { color: chartTheme.crosshairColor, width: 1, style: 3 },
            horzLine: { color: chartTheme.crosshairColor, width: 1, style: 3 },
          }}
          timeScale={{
            timeVisible: true,
            secondsVisible: false,
            borderColor: chartTheme.gridColor,
          }}
          rightPriceScale={{
            borderColor: chartTheme.gridColor,
          }}
          onCreateChart={(_chart) => {
            // Chart ref available for future use (drawing tools, etc.)
          }}
        >
          {/* Candlestick Series */}
          <TimeChart.Series
            type="Candlestick"
            data={candleData()}
            upColor={chartTheme.upColor}
            downColor={chartTheme.downColor}
            wickUpColor={chartTheme.upWickColor}
            wickDownColor={chartTheme.downWickColor}
            borderVisible={false}
            onCreateSeries={(s) => { candleSeries = s; }}
          />

          {/* EMA 9 */}
          <TimeChart.Series
            type="Line"
            data={ema9Data()}
            color={indicatorColors.ema9}
            lineWidth={1}
            crosshairMarkerVisible={false}
            lastValueVisible={false}
            priceLineVisible={false}
          />

          {/* EMA 21 */}
          <TimeChart.Series
            type="Line"
            data={ema21Data()}
            color={indicatorColors.ema21}
            lineWidth={1}
            crosshairMarkerVisible={false}
            lastValueVisible={false}
            priceLineVisible={false}
          />

          {/* SMA 50 */}
          <TimeChart.Series
            type="Line"
            data={sma50Data()}
            color={indicatorColors.sma50}
            lineWidth={1}
            crosshairMarkerVisible={false}
            lastValueVisible={false}
            priceLineVisible={false}
          />

          {/* VWAP */}
          <TimeChart.Series
            type="Line"
            data={vwapData()}
            color={indicatorColors.vwap}
            lineWidth={2}
            lineStyle={0}
            crosshairMarkerVisible={false}
            lastValueVisible={false}
            priceLineVisible={false}
          />

          {/* Bollinger Upper */}
          <TimeChart.Series
            type="Line"
            data={bbData().upper}
            color={indicatorColors.bbUpper}
            lineWidth={1}
            lineStyle={2}
            crosshairMarkerVisible={false}
            lastValueVisible={false}
            priceLineVisible={false}
          />

          {/* Bollinger Lower */}
          <TimeChart.Series
            type="Line"
            data={bbData().lower}
            color={indicatorColors.bbLower}
            lineWidth={1}
            lineStyle={2}
            crosshairMarkerVisible={false}
            lastValueVisible={false}
            priceLineVisible={false}
          />

          {/* Volume — separate pane */}
          <TimeChart.Pane>
            <TimeChart.Series
              type="Histogram"
              data={volumeData()}
              priceFormat={{ type: 'volume' }}
              priceScaleId="volume"
              onCreateSeries={(s) => {
                volumeSeries = s;
                s.priceScale().applyOptions({
                  scaleMargins: { top: 0.7, bottom: 0 },
                });
              }}
            />
          </TimeChart.Pane>

          {/* RSI — separate pane */}
          <TimeChart.Pane>
            <TimeChart.Series
              type="Line"
              data={rsiData()}
              color={indicatorColors.rsi}
              lineWidth={1}
              priceScaleId="rsi"
              lastValueVisible={true}
              priceLineVisible={false}
              onCreateSeries={(s) => {
                s.priceScale().applyOptions({
                  scaleMargins: { top: 0.1, bottom: 0.1 },
                  autoScale: true,
                });
                // Add RSI reference lines (30/70) via price lines
                s.createPriceLine({ price: 70, color: 'rgba(255,80,0,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
                s.createPriceLine({ price: 30, color: 'rgba(0,200,5,0.3)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
                s.createPriceLine({ price: 50, color: 'rgba(255,255,255,0.08)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
              }}
            />
          </TimeChart.Pane>
        </TimeChart>
      </div>
    </div>
  );
};
