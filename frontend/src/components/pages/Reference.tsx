import { type Component } from 'solid-js';
import {
  OptionsChainPanel,
  IVDashboardPanel,
  OptionsSnapshotPanel,
  GexPanel,
  ExpectedMovePanel,
  UnusualActivityPanel,
  PortfolioGreeksPanel,
  SectorRotationPanel,
  KeyLevelsPanel,
} from '../panels/ReferencePanel';

const tile = 'rounded-lg border border-border-default bg-surface-1 overflow-hidden';

export const Reference: Component = () => {
  return (
    <div class="h-full grid grid-cols-3 grid-rows-3 p-2 gap-2 bg-surface-0">
      <div class={tile}><OptionsChainPanel /></div>
      <div class={tile}><IVDashboardPanel /></div>
      <div class={tile}><OptionsSnapshotPanel /></div>
      <div class={tile}><GexPanel /></div>
      <div class={tile}><ExpectedMovePanel /></div>
      <div class={tile}><UnusualActivityPanel /></div>
      <div class={tile}><PortfolioGreeksPanel /></div>
      <div class={tile}><SectorRotationPanel /></div>
      <div class={tile}><KeyLevelsPanel /></div>
    </div>
  );
};
