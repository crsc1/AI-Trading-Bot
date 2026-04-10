import { type Component, type JSX, Show } from 'solid-js';

interface SidebarGroupProps {
  label: string;
  expanded: boolean;
  children: JSX.Element;
}

export const SidebarGroup: Component<SidebarGroupProps> = (props) => {
  return (
    <section class="space-y-1">
      <Show when={props.expanded}>
        <div class="px-3 pt-3 pb-1">
          <span class="font-display text-[9px] uppercase tracking-[0.18em] text-text-muted">
            {props.label}
          </span>
        </div>
      </Show>
      <div class="space-y-1">{props.children}</div>
    </section>
  );
};
