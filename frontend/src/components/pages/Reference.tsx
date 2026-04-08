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
    <div class="h-full flex flex-col">
      <div class="px-6 py-4">
        <h1 class="font-display text-[18px] font-medium">Reference Data</h1>
      </div>
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
