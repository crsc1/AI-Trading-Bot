import { type Component, createEffect, on } from 'solid-js';
import { market } from '../../signals/market';
import { loadCandles } from '../../lib/data';
import { CandleChart } from '../charts/CandleChart';

export const Charts: Component = () => {
  createEffect(
    on(() => market.timeframe, () => loadCandles(), { defer: true })
  );

  return (
    <div class="h-full flex flex-col">
      <CandleChart />
    </div>
  );
};
