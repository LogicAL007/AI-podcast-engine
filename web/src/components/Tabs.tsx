import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabSpec {
  id: string;
  label: string;
}

/** WAI-ARIA tabs: arrow keys move between tabs, and only the active tab is in the tab order. */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
  children,
}: {
  tabs: TabSpec[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  children: ReactNode;
}) {
  const base = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    const target = moves[event.key];
    if (target === undefined) return;
    event.preventDefault();
    const next = (target + tabs.length) % tabs.length;
    onChange(tabs[next].id);
    refs.current[next]?.focus();
  }

  return (
    <div>
      <div className="tabs" role="tablist" aria-label={label}>
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(element) => {
              refs.current[index] = element;
            }}
            id={`${base}-tab-${tab.id}`}
            className="tab"
            role="tab"
            type="button"
            aria-selected={tab.id === active}
            aria-controls={`${base}-panel`}
            tabIndex={tab.id === active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        id={`${base}-panel`}
        className="tab-panel"
        role="tabpanel"
        aria-labelledby={`${base}-tab-${active}`}
        tabIndex={0}
      >
        <div key={active} className="tab-panel-inner">
          {children}
        </div>
      </div>
    </div>
  );
}
