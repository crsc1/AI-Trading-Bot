import { type Component, type JSX, For, Show } from 'solid-js';

export interface TableColumn {
  label: string;
  width?: string;
  align?: 'left' | 'right' | 'center';
  class?: string;
}

interface TableShellProps {
  columns: TableColumn[];
  showHeader?: boolean;
  class?: string;
  tableClass?: string;
  rowClass?: string;
  children: JSX.Element;
}

const alignClass: Record<NonNullable<TableColumn['align']>, string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

export const TableShell: Component<TableShellProps> = (props) => (
  <div class={`flex-1 min-h-0 overflow-auto ${props.class || ''}`}>
    <table class={`w-full table-fixed ${props.tableClass || ''}`}>
      <Show when={props.columns.length > 0}>
        <colgroup>
          <For each={props.columns}>
            {(column) => <col style={column.width ? { width: column.width } : undefined} />}
          </For>
        </colgroup>
      </Show>

      <Show when={props.showHeader !== false}>
        <thead class="sticky top-0 z-10 bg-[#050608]">
          <tr class={`border-b-[1.5px] border-border-default text-[10px] font-display font-semibold uppercase tracking-[0.16em] text-text-secondary ${props.rowClass || ''}`}>
            <For each={props.columns}>
              {(column) => (
                <th class={`px-4 py-3 ${alignClass[column.align || 'left']} ${column.class || ''}`}>
                  {column.label}
                </th>
              )}
            </For>
          </tr>
        </thead>
      </Show>

      <tbody>{props.children}</tbody>
    </table>
  </div>
);
