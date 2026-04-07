import { type Component } from 'solid-js';
import {
  GexPanel,
  VolumeProfilePanel,
  GreeksSurfacePanel,
  SectorPanel,
  MarketInternalsPanel,
  CalendarPanel,
} from '../panels/ReferencePanel';

export const Reference: Component = () => {
  return (
    <div class="h-screen flex flex-col bg-surface-0 text-text-primary font-mono text-[11px]">
      {/* Top Bar */}
      <header class="h-9 flex items-center justify-between px-3 bg-surface-1 border-b border-border-default shrink-0">
        <div class="flex items-center gap-3">
          <span class="text-[13px] font-semibold">Reference Data</span>
        </div>
        <a href="/" class="text-accent hover:text-accent-hover text-[9px]">Back to Dashboard</a>
      </header>

      {/* Grid of data panels */}
      <div class="flex-1 grid grid-cols-2 grid-rows-3 gap-px bg-border-default p-px overflow-auto">
        <div class="bg-surface-1"><GexPanel /></div>
        <div class="bg-surface-1"><VolumeProfilePanel /></div>
        <div class="bg-surface-1"><GreeksSurfacePanel /></div>
        <div class="bg-surface-1"><SectorPanel /></div>
        <div class="bg-surface-1"><MarketInternalsPanel /></div>
        <div class="bg-surface-1"><CalendarPanel /></div>
      </div>
    </div>
  );
};
