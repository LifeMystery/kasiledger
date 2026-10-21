"use client";

import { useState } from "react";
import { rand } from "@/lib/api";
import styles from "./SalesChart.module.css";

type Day = { date: string; sales: number; card_qr: number };

const CASH = "#1E7A4F";
const CARD = "#4A7FB5";

/** Daily sales, split into cash and card/QR-backed, as stacked bars with hover details. */
export default function SalesChart({ days }: { days: Day[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 900;
  const H = 220;
  const pad = { l: 52, r: 8, t: 10, b: 26 };
  const max = Math.max(1, ...days.map((d) => d.sales));
  const nice = Math.ceil(max / 1000) * 1000;
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const step = iw / Math.max(days.length, 1);
  const bw = Math.max(step - 2, 1);
  const y = (v: number) => pad.t + ih - (v / nice) * ih;
  const ticks = [0, nice / 2, nice];
  const active = hover !== null ? days[hover] : null;

  return (
    <figure className={styles.figure}>
      <div className={styles.legend}>
        <span>
          <i style={{ background: CASH }} /> Cash and other sales
        </span>
        <span>
          <i style={{ background: CARD }} /> Matched to card/QR payments
        </span>
      </div>
      <div className={styles.wrap}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily sales for the last 90 days" onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className={styles.grid} />
              <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" className={styles.axis}>
                {t >= 1000 ? `R${t / 1000}k` : `R${t}`}
              </text>
            </g>
          ))}
          {days.map((d, i) => {
            const x = pad.l + i * step + 1;
            const backed = Math.min(d.card_qr, d.sales);
            const cash = d.sales - backed;
            const hCash = (cash / nice) * ih;
            const hCard = (backed / nice) * ih;
            const base = pad.t + ih;
            return (
              <g key={d.date} opacity={hover === null || hover === i ? 1 : 0.45}>
                {hCash > 0 && <rect x={x} y={base - hCash} width={bw} height={hCash} fill={CASH} rx={1} />}
                {hCard > 2 && <rect x={x} y={base - hCash - hCard} width={bw} height={hCard - 2} fill={CARD} rx={1} />}
                <rect
                  x={pad.l + i * step}
                  y={pad.t}
                  width={step}
                  height={ih}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onFocus={() => setHover(i)}
                  tabIndex={-1}
                />
              </g>
            );
          })}
          {days
            .filter((_, i) => i % 15 === 0)
            .map((d) => {
              const i = days.indexOf(d);
              return (
                <text key={d.date} x={pad.l + i * step + step / 2} y={H - 6} textAnchor="middle" className={styles.axis}>
                  {new Date(d.date).toLocaleDateString("en-ZA", { day: "numeric", month: "short" })}
                </text>
              );
            })}
        </svg>
        {active && hover !== null && (
          <div
            className={styles.tip}
            style={{ left: `${((pad.l + hover * step + step / 2) / W) * 100}%` }}
            role="status"
          >
            <strong>
              {new Date(active.date).toLocaleDateString("en-ZA", { weekday: "short", day: "numeric", month: "short" })}
            </strong>
            <span className="num">Sales {rand(active.sales)}</span>
            <span className="num">Card/QR {rand(Math.min(active.card_qr, active.sales))}</span>
          </div>
        )}
      </div>
    </figure>
  );
}
