"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useBusiness, useLive } from "@/components/BusinessContext";
import SalesChart from "@/components/SalesChart";
import TrustBar from "@/components/TrustBar";
import { Analytics, API_URL, getJSON, postForm, rand, Trust } from "@/lib/api";
import styles from "./lender.module.css";

const LEVEL_CLASS: Record<string, string> = { High: styles.high, Medium: styles.medium, Low: styles.low };

function monthName(m: string) {
  return new Date(`${m}-01T00:00:00`).toLocaleDateString("en-ZA", { month: "long", year: "numeric" });
}

export default function LenderPage() {
  const { business, error } = useBusiness();
  const [trust, setTrust] = useState<Trust | null>(null);
  const [data, setData] = useState<Analytics | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const csvInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    if (!business) return;
    Promise.all([
      getJSON<Trust>(`/api/businesses/${business.id}/trust`),
      getJSON<Analytics>(`/api/businesses/${business.id}/analytics`),
    ])
      .then(([t, a]) => {
        setTrust(t);
        setData(a);
      })
      .catch(() => setNotice("Couldn't load this business's records from the API."));
  }, [business]);

  useEffect(load, [load]);

  useLive(
    useCallback(
      (e) => {
        if (e.type === "transaction_updated") {
          clearTimeout(timer.current);
          timer.current = setTimeout(load, 400);
        }
      },
      [load],
    ),
  );

  async function importCsv(file: File) {
    if (!business) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await postForm(`/api/businesses/${business.id}/payments/import`, form);
      const r = await res.json();
      setNotice(`Imported ${r.added} payments${r.skipped ? `, skipped ${r.skipped} rows that couldn't be read` : ""}.`);
      load();
    } catch {
      setNotice("Import failed. Use a CSV with the columns date, amount, provider, reference.");
    }
  }

  async function sendSummary() {
    if (!business) return;
    await fetch(`${API_URL}/api/businesses/${business.id}/summary`, { method: "POST" });
    setNotice(`Today's summary was sent to ${business.owner_name || "the owner"}.`);
  }

  if (error) {
    return (
      <main className="page">
        <div className="error-box">{error}</div>
      </main>
    );
  }
  if (!business || !trust || !data) {
    return (
      <main className="page">
        <p className="muted">Loading business records…</p>
      </main>
    );
  }

  const owedTotal = data.outstanding_credit.reduce((s, o) => s + o.amount, 0);
  const owedConfirmed = data.outstanding_credit.reduce((s, o) => s + o.confirmed_amount, 0);

  return (
    <main className="page">
      <header className={styles.header}>
        <div>
          <h1>{business.name}</h1>
          <p className="muted">
            {[business.owner_name, business.business_type, business.location].filter(Boolean).join(", ")}
          </p>
        </div>
        <div className={styles.actions}>
          <button className="btn" type="button" onClick={sendSummary}>
            Send today&apos;s summary
          </button>
          <a className="btn primary" href={`${API_URL}/api/businesses/${business.id}/report.pdf`} target="_blank" rel="noreferrer">
            Download verified report
          </a>
        </div>
      </header>

      {notice && (
        <p className={styles.notice} role="status">
          {notice}{" "}
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss">
            ✕
          </button>
        </p>
      )}

      <section className={styles.trust} aria-labelledby="trust-h">
        <div className={styles.scoreCol}>
          <h2 id="trust-h" className="sr-only">
            Trust score
          </h2>
          <div className={`${styles.score} ${LEVEL_CLASS[trust.level]}`}>
            <span className="num">{trust.score}</span>
            <small>/ 100</small>
          </div>
          <p className={styles.level}>{trust.level} confidence</p>
          <dl className={styles.facts}>
            <div>
              <dt>Estimated monthly revenue</dt>
              <dd className="num">{rand(trust.estimated_monthly_revenue)}</dd>
            </div>
            <div>
              <dt>Sales in the last {trust.period_days} days</dt>
              <dd className="num">{rand(trust.revenue_in_period)}</dd>
            </div>
          </dl>
        </div>
        <div className={styles.evidence}>
          <h2>Where the score comes from</h2>
          <TrustBar trust={trust} />
        </div>
      </section>

      <section className={styles.block}>
        <h2>Daily sales, last 90 days</h2>
        <SalesChart days={data.daily} />
      </section>

      <section className={styles.block}>
        <h2>Entries flagged for review</h2>
        {trust.flags.length === 0 ? (
          <p className="muted">Nothing flagged. Sales match stock purchases and the shop&apos;s usual pattern.</p>
        ) : (
          <ul className={styles.flags}>
            {trust.flags.map((f) => (
              <li key={f.transaction_id}>
                <div className={styles.flagTop}>
                  <span className="num">{new Date(f.created_at).toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" })}</span>
                  <strong className="num">{rand(f.total, 2)}</strong>
                </div>
                <p className={styles.flagText}>“{f.raw_text}”</p>
                {f.reasons.map((r) => (
                  <p key={r} className={styles.flagReason}>
                    {r}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className={styles.columns}>
        <section className={styles.block}>
          <h2>Monthly trading</h2>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Month</th>
                <th>Sales</th>
                <th>Stock bought</th>
                <th>Expenses</th>
              </tr>
            </thead>
            <tbody>
              {data.monthly.map((m) => (
                <tr key={m.month}>
                  <td>{monthName(m.month)}</td>
                  <td className="num">{rand(m.sales)}</td>
                  <td className="num">{rand(m.purchases)}</td>
                  <td className="num">{rand(m.expenses)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className={styles.block}>
          <h2>Best sellers</h2>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Product</th>
                <th>Units</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {data.top_items.map((it) => (
                <tr key={it.name}>
                  <td className={styles.cap}>{it.name}</td>
                  <td className="num">{it.quantity}</td>
                  <td className="num">{rand(it.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <div className={styles.columns}>
        <section className={styles.block}>
          <h2>Money owed by customers</h2>
          {data.outstanding_credit.length === 0 ? (
            <p className="muted">Nobody owes this business money.</p>
          ) : (
            <>
              <p className="muted">
                {rand(owedTotal)} outstanding, {rand(owedConfirmed)} of it confirmed by the customers themselves.
              </p>
              <table className={styles.table}>
                <tbody>
                  {data.outstanding_credit.map((o) => (
                    <tr key={o.customer}>
                      <td>{o.customer}</td>
                      <td>{o.confirmed ? "Confirmed by customer" : "Not yet confirmed"}</td>
                      <td className="num">{rand(o.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>

        <section className={styles.block}>
          <h2>Add payment evidence</h2>
          <p className="muted">
            Upload a card or QR payment statement (Yoco, SnapScan, Zapper or a bank export) as a CSV with the columns
            date, amount, provider, reference. Matched payments raise the trust score.
          </p>
          <div className={styles.importRow}>
            <button className="btn" type="button" onClick={() => csvInput.current?.click()}>
              Import payments CSV
            </button>
            <a href={`${API_URL}/api/businesses/${business.id}/payments/sample.csv`}>Sample file</a>
            <input
              ref={csvInput}
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importCsv(f);
                e.target.value = "";
              }}
            />
          </div>
        </section>
      </div>
    </main>
  );
}
