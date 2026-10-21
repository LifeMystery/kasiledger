import { Trust } from "@/lib/api";
import styles from "./TrustBar.module.css";

/** The trust score as 100 points of evidence: each component fills its share, gaps show what's missing. */
export default function TrustBar({ trust }: { trust: Trust }) {
  return (
    <div>
      <div className={styles.bar} role="img" aria-label={`Trust score ${trust.score} out of 100`}>
        {trust.components.map((c) => (
          <div key={c.key} className={styles.slot} style={{ flexGrow: c.max }} title={`${c.label}: ${c.points} of ${c.max}`}>
            <div className={styles.fill} style={{ width: `${(c.points / c.max) * 100}%` }} />
          </div>
        ))}
      </div>
      <ul className={styles.list}>
        {trust.components.map((c) => (
          <li key={c.key}>
            <div className={styles.row}>
              <span className={styles.label}>{c.label}</span>
              <span className="num">
                <strong>{c.points}</strong> / {c.max}
              </span>
            </div>
            <p className={styles.detail}>{c.detail}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
