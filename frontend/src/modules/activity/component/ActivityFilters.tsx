"use client";

export type EventFilter = "all" | "verdicts" | "versions" | "skills";

const TABS: Array<{ id: EventFilter; label: string }> = [
  { id: "all", label: "Everything" },
  { id: "verdicts", label: "Audit verdicts" },
  { id: "versions", label: "Versions published" },
  { id: "skills", label: "Skills registered" },
];

/**
 * Which kinds of event to show.
 *
 * "Audit verdicts" is the one that earns this control: two thirds of the feed
 * is registration traffic, and the moment a verdict was written is the only
 * line that carries a judgement. Each tab shows its count so an empty result
 * is obviously an empty category rather than a broken filter.
 */
export function ActivityFilters({
  value,
  onChange,
  counts,
}: {
  value: EventFilter;
  onChange: (next: EventFilter) => void;
  counts: Record<EventFilter, number>;
}) {
  return (
    <div role="tablist" aria-label="Event kind" className="flex flex-wrap gap-2">
      {TABS.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.id)}
            className={
              active
                ? "rounded-4xl border border-hairline-strong bg-elevated px-3 py-1 text-sm text-text"
                : "rounded-4xl border border-border px-3 py-1 text-sm text-text-secondary transition-colors hover:border-hairline-strong hover:text-text"
            }
          >
            {tab.label}
            <span className="numeric ml-1.5 text-xs text-text-tertiary">
              {counts[tab.id]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
