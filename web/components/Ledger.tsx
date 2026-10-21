"use client";

import { useCallback, useEffect, useState } from "react";
import { getJSON, rand, time, Transaction } from "@/lib/api";
import { LiveEvent } from "@/lib/live";
import { useLive } from "./BusinessContext";
import styles from "./Ledger.module.css";

const SOURCE_LABEL: Record<string, string> = {
  voice: "🎤 voice note",
  text: "💬 text",
  invoice: "🧾 supplier slip",
  seed: "",
};

const TYPE_LABEL: Record<string, string> = {
  sale: "Sale",
  purchase: "Stock bought",
  expense: "Expense",
  repayment: "Paid back",
};

function describe(tx: Transaction): string {
  if (tx.items.length) {
    return tx.items.map((i) => `${i.quantity} × ${i.name}`).join(", ");
  }
  return tx.note || (tx.customer ? `from ${tx.customer}` : "");
}

export default function Ledger({ businessId, limit = 40 }: { businessId: number; limit?: number }) {
  const [rows, setRows] = useState<Transaction[]>([]);
  const [fresh, setFresh] = useState<Set<number>>(new Set());

  useEffect(() => {
    getJSON<Transaction[]>(`/api/businesses/${businessId}/transactions?limit=${limit}`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [businessId, limit]);

  useLive(
    useCallback(
      (e: LiveEvent) => {
        if (e.type !== "transaction" && e.type !== "transaction_updated") return;
        const tx = e.transaction;
        if (tx.business_id !== businessId) return;
        setRows((current) => {
          const without = current.filter((r) => r.id !== tx.id);
          if (tx.status === "discarded") return without;
          const exists = without.length !== current.length;
          const next = exists ? current.map((r) => (r.id === tx.id ? tx : r)) : [tx, ...current];
          return next.slice(0, limit);
        });
        setFresh((s) => new Set(s).add(tx.id));
        setTimeout(
          () =>
            setFresh((s) => {
              const n = new Set(s);
              n.delete(tx.id);
              return n;
            }),
          3500,
        );
      },
      [businessId, limit],
    ),
  );

  return (
    <div className={styles.book}>
      <div className={styles.head} aria-hidden>
        <span>Time</span>
        <span>Entry</span>
        <span className={styles.right}>Amount</span>
      </div>
      <ol className={styles.lines}>
        {rows.length === 0 && <li className={styles.emptyLine}>No entries yet. Send a sale from the phone.</li>}
        {rows.map((tx) => {
          const classes = [styles.line];
          if (tx.status === "flagged") classes.push(styles.flagged);
          if (tx.status === "pending") classes.push(styles.pending);
          if (fresh.has(tx.id)) classes.push(styles.fresh);
          const outflow = tx.type === "purchase" || tx.type === "expense";
          return (
            <li key={tx.id} className={classes.join(" ")}>
              <span className={`${styles.time} num`}>{time(tx.created_at)}</span>
              <span className={styles.entry}>
                <span className={styles.what}>
                  <strong>{tx.on_credit ? "Sale on credit" : TYPE_LABEL[tx.type]}</strong> {describe(tx)}
                  {tx.on_credit && tx.customer && (
                    <span className={tx.credit_confirmed ? styles.okTag : styles.waitTag}>
                      {tx.customer} {tx.credit_confirmed ? "confirmed ✓" : "to confirm"}
                    </span>
                  )}
                  {tx.status === "pending" && <span className={styles.waitTag}>waiting for owner to confirm</span>}
                </span>
                {SOURCE_LABEL[tx.source] && <span className={styles.source}>{SOURCE_LABEL[tx.source]}</span>}
                {tx.status === "flagged" &&
                  tx.flags.map((f) => (
                    <span key={f.code} className={styles.reason}>
                      ⚠ {f.message}
                    </span>
                  ))}
              </span>
              <span className={`${styles.amount} num ${outflow ? styles.out : ""}`}>
                {outflow ? "−" : ""}
                {rand(tx.total, 2)}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
