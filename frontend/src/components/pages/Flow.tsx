import { type Component, createSignal, Show } from 'solid-js';
import { OrderFlowChart } from '../charts/OrderFlowChart';
import { OptionsBubbleChart } from '../charts/OptionsBubbleChart';
import { OptionsFlow } from '../charts/OptionsFlow';
import { OptionsHeatmap } from '../charts/OptionsHeatmap';

type FlowView = 'options' | 'equity';

export const Flow: Component = () => {
  const [view, setView] = createSignal<FlowView>('options');

  return (
    <div class="h-full flex flex-col">
      {/* View toggle */}
      <div class="h-10 flex items-center gap-2 px-4 bg-surface-1 border-b border-border-default shrink-0 font-display">
        <button
          class={`px-3 py-1 text-[11px] rounded transition-colors ${
            view() === 'options'
              ? 'bg-accent text-white'
              : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
          }`}
          onClick={() => setView('options')}
        >
          Options Flow
        </button>
        <button
          class={`px-3 py-1 text-[11px] rounded transition-colors ${
            view() === 'equity'
              ? 'bg-accent text-white'
              : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
          }`}
          onClick={() => setView('equity')}
        >
          Equity Flow
        </button>
      </div>

      {/* Content */}
      <div class="flex-1 min-h-0">
        <Show when={view() === 'options'}>
          <div class="h-full flex flex-col p-1.5 gap-1.5 bg-surface-0">
            {/* Bubble chart — top panel */}
            <div class="flex-[45] min-h-0 rounded-lg border border-border-default bg-surface-1 overflow-hidden">
              <OptionsBubbleChart />
            </div>
            {/* Tape + Heatmap — bottom panels side by side */}
            <div class="flex-[55] min-h-0 flex gap-1.5">
              <div class="flex-[55] min-w-0 rounded-lg border border-border-default bg-surface-1 overflow-hidden">
                <OptionsFlow />
              </div>
              <div class="flex-[45] min-w-0 rounded-lg border border-border-default bg-surface-1 overflow-hidden">
                <OptionsHeatmap />
              </div>
            </div>
          </div>
        </Show>

        <Show when={view() === 'equity'}>
          <OrderFlowChart />
        </Show>
      </div>
    </div>
  );
};
