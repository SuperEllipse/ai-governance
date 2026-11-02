import { useRef, useState } from "react";

interface Datum {
  label: string;
  value: number;
}

interface Tip {
  x: number;
  y: number;
  text: string;
}

/**
 * Single-series horizontal bar chart in plain HTML: one hue, value at the bar tip,
 * hover/focus tooltip, and a table view of the same numbers.
 */
export function BarChart({ title, data, unit }: { title: string; data: Datum[]; unit: string }) {
  const [asTable, setAsTable] = useState(false);
  const [tip, setTip] = useState<Tip | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const max = Math.max(1, ...data.map((d) => d.value));
  const total = data.reduce((sum, d) => sum + d.value, 0);

  const describe = (d: Datum) => {
    const share = total ? ` (${Math.round((d.value / total) * 100)}% of ${unit})` : "";
    return `${d.label}: ${d.value.toLocaleString()}${share}`;
  };

  const showTip = (el: HTMLElement, d: Datum) => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const bar = el.querySelector(".bar") as HTMLElement | null;
    const target = (bar ?? el).getBoundingClientRect();
    const box = wrap.getBoundingClientRect();
    setTip({ x: target.right - box.left, y: target.top - box.top, text: describe(d) });
  };

  return (
    <div className="card">
      <div className="card-title">
        <h3>{title}</h3>
        <button className="btn-link" style={{ marginLeft: "auto" }} onClick={() => setAsTable((v) => !v)}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {data.length === 0 ? (
        <p className="empty">No {unit} recorded.</p>
      ) : asTable ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th style={{ textAlign: "right" }}>Count</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.label}>
                  <td>{d.label}</td>
                  <td className="num">{d.value.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bars" ref={wrapRef} role="list" aria-label={title} onMouseLeave={() => setTip(null)}>
          {data.map((d) => (
            <div
              key={d.label}
              className="bar-row"
              role="listitem"
              tabIndex={0}
              aria-label={describe(d)}
              onMouseEnter={(e) => showTip(e.currentTarget, d)}
              onFocus={(e) => showTip(e.currentTarget, d)}
              onBlur={() => setTip(null)}
            >
              <span className="bar-label" title={d.label}>
                {d.label}
              </span>
              <span className="bar-track">
                <span className="bar" style={{ width: `calc((100% - 48px) * ${d.value / max})` }} />
                <span className="bar-value">{d.value.toLocaleString()}</span>
              </span>
            </div>
          ))}
          {tip && (
            <div className="tooltip" style={{ left: tip.x, top: tip.y }} role="presentation">
              {tip.text}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
