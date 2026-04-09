/**
 * Per-indicator settings state — persisted to localStorage.
 * Each indicator can have custom parameters (length, multiplier, source, etc.)
 * that override the defaults from the registry.
 */
import { createStore } from 'solid-js/store';

export interface IndicatorParam {
  name: string;
  label: string;
  type: 'int' | 'float' | 'select';
  value: any;
  defaultValue: any;
  min?: number;
  max?: number;
  step?: number;
  options?: { label: string; value: any }[];
}

export interface IndicatorConfig {
  params: IndicatorParam[];
}

// Custom indicator configs (not from the library)
export const CUSTOM_CONFIGS: Record<string, IndicatorConfig> = {
  'aavwap': {
    params: [
      { name: 'anchor', label: 'Starting Point', type: 'select', value: 'highest_high', defaultValue: 'highest_high',
        options: [
          { label: 'Highest High', value: 'highest_high' },
          { label: 'Lowest Low', value: 'lowest_low' },
          { label: 'Session Open', value: 'session_open' },
        ]},
      { name: 'lookback', label: 'Starting Point Length', type: 'int', value: 1000, defaultValue: 1000, min: 10, max: 5000, step: 10 },
      { name: 'band1Mult', label: 'Band 1 Multiplier', type: 'float', value: 1, defaultValue: 1, min: 0.1, max: 10, step: 0.1 },
      { name: 'band2Mult', label: 'Band 2 Multiplier', type: 'float', value: 2, defaultValue: 2, min: 0.1, max: 10, step: 0.1 },
      { name: 'band3Mult', label: 'Band 3 Multiplier', type: 'float', value: 3, defaultValue: 3, min: 0.1, max: 10, step: 0.1 },
    ],
  },
  'vwap-bands': {
    params: [
      { name: 'band1Mult', label: 'Band 1 Multiplier', type: 'float', value: 1, defaultValue: 1, min: 0.1, max: 10, step: 0.1 },
      { name: 'band2Mult', label: 'Band 2 Multiplier', type: 'float', value: 2, defaultValue: 2, min: 0.1, max: 10, step: 0.1 },
      { name: 'band3Mult', label: 'Band 3 Multiplier', type: 'float', value: 3, defaultValue: 3, min: 0.1, max: 10, step: 0.1 },
    ],
  },
  'bollinger-bands': {
    params: [
      { name: 'length', label: 'Length', type: 'int', value: 20, defaultValue: 20, min: 2, max: 500, step: 1 },
      { name: 'mult', label: 'Multiplier', type: 'float', value: 2, defaultValue: 2, min: 0.1, max: 10, step: 0.1 },
    ],
  },
};

// State
type SettingsState = Record<string, Record<string, any>>;

function loadSaved(): SettingsState {
  try {
    const raw = localStorage.getItem('chart-indicator-settings');
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

const [settings, setSettings] = createStore<SettingsState>(loadSaved());

export { settings as indicatorSettings };

function persist() {
  try { localStorage.setItem('chart-indicator-settings', JSON.stringify(settings)); } catch {}
}

export function setIndicatorParam(id: string, param: string, value: any) {
  if (!settings[id]) setSettings(id, {});
  setSettings(id, param, value);
  persist();
}

export function getIndicatorParams(id: string): Record<string, any> {
  return settings[id] || {};
}

export function resetIndicatorSettings(id: string) {
  setSettings(id, {});
  persist();
}

export function getConfigForIndicator(id: string): IndicatorConfig | null {
  return CUSTOM_CONFIGS[id] || null;
}
