"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useBusiness, useLive } from "@/components/BusinessContext";
import Ledger from "@/components/Ledger";
import Phone from "@/components/Phone";
import { DaySummary, getJSON, rand } from "@/lib/api";
import styles from "./live.module.css";

const OWNER_REPLIES = [
  { label: "Sale", text: "sale bread 3 18" },
  { label: "isiZulu sale", text: "Ngithengise izinkwa ezimbili ne-cooldrink, R66" },
  { label: "Save (1)", text: "1" },
  { label: "Fix (2)", text: "2" },
  { label: "Fake big sale", text: "sale bread 500 18" },
  { label: "Credit", text: "owe Sipho 40 0821110001" },
  { label: "Summary", text: "summary" },
  { label: "Stock", text: "stock" },
  { label: "Owed", text: "owed" },
  { label: "Score", text: "score" },
  { label: "Report", text: "report" },
];

const CUSTOMER_REPLIES = [
  { label: "Yes", text: "YES" },
  { label: "No", text: "NO" },
];

export default function LivePage() {
  const { business, error } = useBusiness();
  const [who, setWho] = useState<"owner" | "customer">("owner");
  const [today, setToday] = useState<DaySummary | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const loadToday = useCallback(() => {
    if (!business) return;
    getJSON<{ today: DaySummary }>(`/api/businesses/${business.id}`)
      .then((d) => setToday(d.today))
      .catch(() => setToday(null));
  }, [business]);

  useEffect(loadToday, [loadToday]);

  useLive(
    useCallback(
      (e) => {
        if (e.type === "transaction" || e.type === "transaction_updated") {
          clearTimeout(timer.current);
          timer.current = setTimeout(loadToday, 300);
        }
      },
      [loadToday],
    ),
  );

  if (error) {
    return (
      <main className="page">
        <div className="error-box">{error}</div>
      </main>
    );
  }

  const ownerPhone = business?.channel === "sim" ? business.address.slice(4) : "+27820000001";

  return (
    <main className={`page ${styles.grid}`}>
      <section className={styles.phoneCol} aria-label="Phone simulator">
        <div className={styles.switch} role="tablist" aria-label="Whose phone">
          <button role="tab" aria-selected={who === "owner"} onClick={() => setWho("owner")}>
            Owner&apos;s phone
          </button>
          <button role="tab" aria-selected={who === "customer"} onClick={() => setWho("customer")}>
            Customer (Sipho)
          </button>
        </div>
        {who === "owner" ? (
          <Phone key="owner" phone={ownerPhone} contactName={business?.owner_name || "Owner"} quickReplies={OWNER_REPLIES} />
        ) : (
          <Phone key="customer" phone="+27821110001" contactName="Sipho" quickReplies={CUSTOMER_REPLIES} showTools={false} />
        )}
      </section>

      <section className={styles.bookCol} aria-label="Live ledger">
        <div className={styles.title}>
          <h1>{business?.name ?? "Loading…"}</h1>
          {business && (
            <p className="muted">
              {[business.business_type, business.location].filter(Boolean).join(", ")}
            </p>
          )}
        </div>

        {today && (
          <dl className={styles.today}>
            <div>
              <dt>Sales today</dt>
              <dd className="num">{rand(today.revenue)}</dd>
            </div>
            <div>
              <dt>Estimated profit</dt>
              <dd className="num">{rand(today.estimated_profit)}</dd>
            </div>
            <div>
              <dt>Sales recorded</dt>
              <dd className="num">{today.sales_count}</dd>
            </div>
            <div className={today.flagged ? styles.alert : undefined}>
              <dt>Flagged today</dt>
              <dd className="num">{today.flagged}</dd>
            </div>
          </dl>
        )}

        <h2 className={styles.bookTitle}>Counter book</h2>
        {business ? <Ledger businessId={business.id} /> : <p className="muted">No businesses yet. Send “hi” from the phone.</p>}
      </section>
    </main>
  );
}
