/**
 * Indicator Settings Panel — popover for configuring indicator parameters.
 * Renders dynamic form controls based on the indicator's config.
 */
import { type Component, For, Show, onCleanup } from 'solid-js';
import {
  getConfigForIndicator,
  getIndicatorParams,
  setIndicatorParam,
  resetIndicatorSettings,
  type IndicatorParam,
} from '../../signals/indicatorSettings';

interface Props {
  indicatorId: string;
  onClose: () => void;
  onApply: () => void;
}

export const IndicatorSettingsPanel: Component<Props> = (props) => {
  let panelRef: HTMLDivElement | undefined;

  const config = () => getConfigForIndicator(props.indicatorId);
  const saved = () => getIndicatorParams(props.indicatorId);

  const getValue = (param: IndicatorParam) => {
    const s = saved();
    return s[param.name] !== undefined ? s[param.name] : param.defaultValue;
  };

  const handleChange = (param: IndicatorParam, value: any) => {
    let parsed = value;
    if (param.type === 'int') parsed = parseInt(value) || param.defaultValue;
    if (param.type === 'float') parsed = parseFloat(value) || param.defaultValue;
    setIndicatorParam(props.indicatorId, param.name, parsed);
    props.onApply();
  };

  const handleReset = () => {
    resetIndicatorSettings(props.indicatorId);
    props.onApply();
  };

  // Close on click outside
  const handleClickOutside = (e: MouseEvent) => {
    if (panelRef && !panelRef.contains(e.target as Node)) props.onClose();
  };
  document.addEventListener('mousedown', handleClickOutside);
  onCleanup(() => document.removeEventListener('mousedown', handleClickOutside));

  // Close on Escape
  const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') props.onClose(); };
  document.addEventListener('keydown', handleKey);
  onCleanup(() => document.removeEventListener('keydown', handleKey));

  return (
    <Show when={config()}>
      <div
        ref={panelRef}
        class="absolute left-0 top-full mt-1 z-50 bg-surface-1 border border-border-default rounded-lg shadow-xl min-w-[240px] p-3"
      >
        <div class="flex items-center justify-between mb-3">
          <span class="font-display text-[11px] font-medium text-text-primary uppercase tracking-wider">Settings</span>
          <button
            onClick={props.onClose}
            class="text-text-muted hover:text-text-secondary text-[12px] cursor-pointer"
          >✕</button>
        </div>

        <div class="space-y-3">
          <For each={config()!.params}>
            {(param) => (
              <div>
                <label class="block font-display text-[10px] text-text-secondary mb-1">{param.label}</label>

                <Show when={param.type === 'select'}>
                  <select
                    value={getValue(param)}
                    onChange={(e) => handleChange(param, e.currentTarget.value)}
                    class="w-full bg-surface-2 border border-border-default rounded px-2 py-1.5 text-[11px] font-data text-text-primary outline-none focus:border-accent cursor-pointer"
                  >
                    <For each={param.options || []}>
                      {(opt) => <option value={opt.value}>{opt.label}</option>}
                    </For>
                  </select>
                </Show>

                <Show when={param.type === 'int' || param.type === 'float'}>
                  <div class="flex items-center gap-2">
                    <input
                      type="number"
                      value={getValue(param)}
                      min={param.min}
                      max={param.max}
                      step={param.step || (param.type === 'int' ? 1 : 0.1)}
                      onChange={(e) => handleChange(param, e.currentTarget.value)}
                      class="flex-1 bg-surface-2 border border-border-default rounded px-2 py-1.5 text-[11px] font-data text-text-primary outline-none focus:border-accent"
                    />
                    <div class="flex flex-col">
                      <button
                        onClick={() => handleChange(param, getValue(param) + (param.step || 1))}
                        class="text-[8px] text-text-muted hover:text-text-secondary px-1 cursor-pointer"
                      >+</button>
                      <button
                        onClick={() => handleChange(param, getValue(param) - (param.step || 1))}
                        class="text-[8px] text-text-muted hover:text-text-secondary px-1 cursor-pointer"
                      >−</button>
                    </div>
                  </div>
                </Show>
              </div>
            )}
          </For>
        </div>

        <button
          onClick={handleReset}
          class="mt-3 w-full bg-surface-2 hover:bg-surface-3 text-text-secondary text-[10px] font-display py-1.5 rounded transition-colors cursor-pointer"
        >
          Reset
        </button>
      </div>
    </Show>
  );
};
