import { type Component, For, Show, createSignal } from 'solid-js';
import { A, useLocation } from '@solidjs/router';
import { SidebarGroup } from '../system/SidebarGroup';

interface NavItem {
  path: string;
  label: string;
  icon: string;
  group: string;
}

const navItems: NavItem[] = [
  { path: '/', label: 'Dashboard', icon: 'DB', group: 'Trade' },
  { path: '/charts', label: 'Charts', icon: 'CH', group: 'Trade' },
  { path: '/flow', label: 'Order Flow', icon: 'FL', group: 'Flow' },
  { path: '/scanner', label: 'Scanner', icon: 'SC', group: 'Flow' },
  { path: '/agent', label: 'AI Research', icon: 'AI', group: 'Research' },
  { path: '/reference', label: 'Reference', icon: 'RF', group: 'Research' },
];

const groups = ['Trade', 'Flow', 'Research'];

function loadExpandedPreference() {
  try {
    const stored = localStorage.getItem('shell-sidebar-expanded');
    return stored == null ? true : JSON.parse(stored) === true;
  } catch {
    return true;
  }
}

export const Sidebar: Component = () => {
  const [expanded, setExpanded] = createSignal(loadExpandedPreference());
  const location = useLocation();
  const getTestId = (path: string) => path === '/' ? 'nav-dashboard' : `nav-${path.slice(1)}`;

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  const toggleExpanded = () => {
    const next = !expanded();
    setExpanded(next);
    try {
      localStorage.setItem('shell-sidebar-expanded', JSON.stringify(next));
    } catch {}
  };

  return (
    <nav
      data-testid="sidebar"
      class="h-screen flex flex-col bg-[#040506] border-r border-border-default shrink-0 transition-all duration-150 ease-out select-none"
      style={{ width: expanded() ? '228px' : '72px' }}
    >
      <div data-testid="sidebar-brand" class={`h-14 border-b border-border-default flex items-center ${expanded() ? 'justify-between px-4' : 'justify-center px-0'}`}>
        <div class={`flex items-center gap-3 ${expanded() ? '' : 'justify-center'}`}>
          <span class="w-8 h-8 rounded-xl border border-accent/35 bg-accent/14 text-accent flex items-center justify-center font-display text-[11px] tracking-[0.16em]">
            AT
          </span>
          <Show when={expanded()}>
            <div class="min-w-0">
              <div class="font-display text-[13px] text-text-primary font-medium">Atlas Trade</div>
              <div class="font-display text-[9px] uppercase tracking-[0.16em] text-text-muted">Realtime Options</div>
            </div>
          </Show>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2">
        <For each={groups}>
          {(group) => (
            <SidebarGroup label={group} expanded={expanded()}>
              <For each={navItems.filter((item) => item.group === group)}>
                {(item) => (
                  <A
                    href={item.path}
                    aria-label={item.label}
                    data-testid={getTestId(item.path)}
                    class={`flex items-center gap-3 rounded-xl h-11 transition-colors ${
                      expanded() ? 'px-3' : 'justify-center px-0'
                    } ${
                      isActive(item.path)
                        ? 'bg-[#0b0d11] text-text-primary border border-border-default'
                        : 'text-text-secondary hover:bg-[#090b0e] hover:text-text-primary border border-transparent'
                    }`}
                    title={expanded() ? undefined : item.label}
                  >
                    <span class={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 font-display text-[10px] tracking-[0.14em] ${
                      isActive(item.path)
                        ? 'border-accent/40 bg-accent/14 text-accent'
                        : 'border-border-default bg-[#080a0d] text-text-secondary'
                    }`}>
                      {item.icon}
                    </span>
                    <Show when={expanded()}>
                      <div class="min-w-0">
                        <div class="font-display text-[12px] font-medium whitespace-nowrap overflow-hidden">
                          {item.label}
                        </div>
                        <div class="font-display text-[9px] uppercase tracking-[0.14em] text-text-muted">
                          {item.group}
                        </div>
                      </div>
                    </Show>
                  </A>
                )}
              </For>
            </SidebarGroup>
          )}
        </For>
      </div>

      <div class="border-t border-border-default p-2">
        <button
          data-testid="sidebar-toggle"
          aria-label={expanded() ? 'Collapse sidebar' : 'Expand sidebar'}
          onClick={toggleExpanded}
          class={`flex items-center gap-3 rounded-xl h-11 w-full text-text-muted hover:text-text-secondary hover:bg-[#090b0e] transition-colors ${
            expanded() ? 'px-3' : 'justify-center px-0'
          }`}
        >
          <span class="w-8 h-8 rounded-lg border border-border-default bg-[#080a0d] flex items-center justify-center shrink-0 font-display text-[11px]">
            {expanded() ? '<<' : '>>'}
          </span>
          <Show when={expanded()}>
            <div class="min-w-0 text-left">
              <div class="font-display text-[12px] whitespace-nowrap">Collapse</div>
              <div class="font-display text-[9px] uppercase tracking-[0.14em] text-text-muted">Shell</div>
            </div>
          </Show>
        </button>
      </div>
    </nav>
  );
};
