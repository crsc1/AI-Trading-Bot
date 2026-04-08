import { type Component, For, createSignal } from 'solid-js';
import { A, useLocation } from '@solidjs/router';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

const navItems: NavItem[] = [
  { path: '/', label: 'Dashboard', icon: '⊞' },
  { path: '/charts', label: 'Charts', icon: '⊟' },
  { path: '/flow', label: 'Order Flow', icon: '⊡' },
  { path: '/agent', label: 'AI Agent', icon: '◈' },
  { path: '/scanner', label: 'Scanner', icon: '⊛' },
  { path: '/reference', label: 'Reference', icon: '◉' },
];

export const Sidebar: Component = () => {
  const [expanded, setExpanded] = createSignal(false);
  const location = useLocation();

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <nav
      class="h-screen flex flex-col bg-surface-1 border-r border-border-default shrink-0 transition-all duration-150 ease-out select-none"
      style={{ width: expanded() ? '168px' : '48px' }}
    >
      {/* Logo / Brand */}
      <div class="h-12 flex items-center justify-center border-b border-border-default">
        <span class="font-display text-[13px] font-medium text-text-primary">
          {expanded() ? 'AI Bot' : 'A'}
        </span>
      </div>

      {/* Nav Items */}
      <div class="flex-1 flex flex-col gap-1 py-2 px-1.5">
        <For each={navItems}>
          {(item) => (
            <A
              href={item.path}
              class={`flex items-center gap-3 rounded h-10 transition-colors ${
                expanded() ? 'px-3' : 'justify-center px-0'
              } ${
                isActive(item.path)
                  ? 'bg-surface-3 text-text-primary'
                  : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
              }`}
              title={expanded() ? undefined : item.label}
            >
              <span class="text-[16px] w-5 text-center shrink-0">{item.icon}</span>
              {expanded() && (
                <span class="font-display text-[12px] font-medium whitespace-nowrap overflow-hidden">
                  {item.label}
                </span>
              )}
            </A>
          )}
        </For>
      </div>

      {/* Collapse Toggle */}
      <div class="border-t border-border-default py-2 px-1.5">
        <button
          onClick={() => setExpanded(!expanded())}
          class={`flex items-center gap-3 rounded h-10 w-full text-text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors ${
            expanded() ? 'px-3' : 'justify-center px-0'
          }`}
        >
          <span
            class="text-[14px] w-5 text-center shrink-0 transition-transform duration-150"
            style={{ transform: expanded() ? 'rotate(0deg)' : 'rotate(180deg)' }}
          >
            ◂
          </span>
          {expanded() && (
            <span class="font-display text-[11px] whitespace-nowrap">Collapse</span>
          )}
        </button>
      </div>
    </nav>
  );
};
