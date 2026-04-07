/**
 * Reference data panels — GEX, Volume Profile, Greeks, Sectors, Internals, Calendar.
 * Each panel fetches its own data from the backend API.
 */
import { type Component, For, Show, createSignal, onMount, createResource } from 'solid-js';
import { api } from '../../lib/api';

// ── GEX Panel ────────────────────────────────────────────────────────────────

const GexPanel: Component = () => {
  const [gex] = createResource(async () => {
    try {
      return await api.getGex();
    } catch { return null; }
  });

  return (
    <div class="p-3 h-full flex flex-col">
      <div class="text-[10px] font-semibold text-accent mb-2">GEX EXPOSURE</div>
      <Show when={gex()} fallback={<div class="text-text-muted text-[9px]">Loading GEX data...</div>}>
        {(data) => {
          const d = data();
          return (
            <div class="flex-1 overflow-y-auto">
              <div class="grid grid-cols-2 gap-2 text-[9px]">
                <div>
                  <div class="text-text-muted text-[7px]">REGIME</div>
                  <div class={d.regime === 'bullish' ? 'text-positive' : d.regime === 'bearish' ? 'text-negative' : 'text-text-primary'}>
                    {d.regime || 'N/A'}
                  </div>
                </div>
                <div>
                  <div class="text-text-muted text-[7px]">FLIP LEVEL</div>
                  <div>${d.flip_level?.toFixed(2) || 'N/A'}</div>
                </div>
                <div>
                  <div class="text-text-muted text-[7px]">MAX GAMMA</div>
                  <div>${d.max_gamma_strike?.toFixed(2) || 'N/A'}</div>
                </div>
                <div>
                  <div class="text-text-muted text-[7px]">NET GEX</div>
                  <div>{d.current_gex ? `${(d.current_gex / 1e9).toFixed(2)}B` : 'N/A'}</div>
                </div>
              </div>

              <Show when={d.strike_gex}>
                <div class="mt-2 text-[7px] text-text-muted">TOP STRIKES</div>
                <div class="mt-1 space-y-0.5">
                  <For each={Object.entries(d.strike_gex || {}).sort(([, a]: any, [, b]: any) => Math.abs(b) - Math.abs(a)).slice(0, 8)}>
                    {([strike, val]: [string, any]) => (
                      <div class="flex items-center justify-between text-[8px]">
                        <span>${strike}</span>
                        <div class="flex-1 mx-2 h-1 bg-surface-3 rounded overflow-hidden">
                          <div
                            class={`h-full rounded ${Number(val) >= 0 ? 'bg-positive/60' : 'bg-negative/60'}`}
                            style={{ width: `${Math.min(100, Math.abs(Number(val)) / (Math.abs(d.current_gex || 1)) * 50)}%` }}
                          />
                        </div>
                        <span class={Number(val) >= 0 ? 'text-positive' : 'text-negative'}>
                          {(Number(val) / 1e6).toFixed(1)}M
                        </span>
                      </div>
                    )}
                  </For>
                </div>
              </Show>
            </div>
          );
        }}
      </Show>
    </div>
  );
};

// ── Generic Data Panel (for panels that just show key-value data) ─────────

interface DataItem {
  label: string;
  value: string;
  color?: string;
}

const DataGrid: Component<{ title: string; items: DataItem[]; loading?: boolean }> = (props) => {
  return (
    <div class="p-3 h-full flex flex-col">
      <div class="text-[10px] font-semibold text-accent mb-2">{props.title}</div>
      <Show when={!props.loading} fallback={<div class="text-text-muted text-[9px]">Loading...</div>}>
        <div class="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[9px]">
          <For each={props.items}>
            {(item) => (
              <>
                <div class="text-text-muted text-[7px]">{item.label}</div>
                <div class={item.color || 'text-text-primary'}>{item.value}</div>
              </>
            )}
          </For>
        </div>
      </Show>
    </div>
  );
};

// ── Volume Profile Panel ─────────────────────────────────────────────────────

const VolumeProfilePanel: Component = () => {
  return (
    <div class="p-3 h-full flex flex-col">
      <div class="text-[10px] font-semibold text-accent mb-2">VOLUME PROFILE</div>
      <div class="flex-1 flex items-center justify-center text-text-muted text-[9px]">
        Volume profile visualization renders in the order flow chart.
        <br />See the price ladder on the right side of the flow chart.
      </div>
    </div>
  );
};

// ── Greeks Surface Panel ─────────────────────────────────────────────────────

const GreeksSurfacePanel: Component = () => {
  const [data, setData] = createSignal<DataItem[]>([]);
  const [loading, setLoading] = createSignal(true);

  onMount(async () => {
    try {
      const positions = await api.getPositions().catch(() => ({ positions: [] }));
      const items: DataItem[] = [];
      for (const pos of (positions?.positions || []).slice(0, 6)) {
        if (pos.greeks) {
          items.push({ label: `${pos.strike} ${pos.option_type}`, value: '' });
          items.push({ label: 'Delta', value: pos.greeks.delta?.toFixed(3) || 'N/A' });
          items.push({ label: 'Gamma', value: pos.greeks.gamma?.toFixed(4) || 'N/A' });
          items.push({ label: 'Theta', value: pos.greeks.theta?.toFixed(3) || 'N/A', color: 'text-negative' });
          items.push({ label: 'Vega', value: pos.greeks.vega?.toFixed(3) || 'N/A' });
        }
      }
      if (items.length === 0) {
        items.push({ label: 'No positions', value: 'Open a position to see Greeks' });
      }
      setData(items);
    } catch { /* noop */ }
    setLoading(false);
  });

  return <DataGrid title="GREEKS" items={data()} loading={loading()} />;
};

// ── Sector Rotation Panel ────────────────────────────────────────────────────

const SectorPanel: Component = () => {
  return (
    <div class="p-3 h-full flex flex-col">
      <div class="text-[10px] font-semibold text-accent mb-2">SECTOR ROTATION</div>
      <div class="flex-1 flex items-center justify-center text-text-muted text-[9px]">
        Sector data available via /api/signals config.
        <br />Requires sector_monitor data provider.
      </div>
    </div>
  );
};

// ── Market Internals Panel ───────────────────────────────────────────────────

const MarketInternalsPanel: Component = () => {
  return (
    <div class="p-3 h-full flex flex-col">
      <div class="text-[10px] font-semibold text-accent mb-2">MARKET INTERNALS</div>
      <div class="flex-1 flex items-center justify-center text-text-muted text-[9px]">
        TICK, ADD, VOLD breadth data.
        <br />Requires market_internals data provider.
      </div>
    </div>
  );
};

// ── Economic Calendar Panel ──────────────────────────────────────────────────

const CalendarPanel: Component = () => {
  return (
    <div class="p-3 h-full flex flex-col">
      <div class="text-[10px] font-semibold text-accent mb-2">ECONOMIC CALENDAR</div>
      <div class="flex-1 flex items-center justify-center text-text-muted text-[9px]">
        Event calendar available via event_calendar provider.
      </div>
    </div>
  );
};

// ── Export ────────────────────────────────────────────────────────────────────

export {
  GexPanel,
  VolumeProfilePanel,
  GreeksSurfacePanel,
  SectorPanel,
  MarketInternalsPanel,
  CalendarPanel,
};
