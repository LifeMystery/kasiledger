"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useBusiness } from "./BusinessContext";
import styles from "./TopBar.module.css";

const ENGINE_LABELS: Record<string, string> = {
  rule_based: "keyword parser",
  ollama: "local AI (Ollama)",
  local_whisper: "Whisper voice",
  tesseract: "Tesseract slip reader",
};

export default function TopBar() {
  const { businesses, business, setBusinessId, config, connected } = useBusiness();
  const path = usePathname();
  const engines = config
    ? [config.extractor, config.speech, config.ocr].filter((e) => e !== "none").map((e) => ENGINE_LABELS[e] ?? e)
    : [];

  return (
    <header className={styles.bar}>
      <div className={styles.inner}>
        <Link href="/" className={styles.brand} aria-label="KasiLedger home">
          <span className={styles.mark} aria-hidden>
            K
          </span>
          KasiLedger
        </Link>
        <nav className={styles.nav} aria-label="Main">
          <Link href="/" aria-current={path === "/" ? "page" : undefined}>
            Live
          </Link>
          <Link href="/lender" aria-current={path === "/lender" ? "page" : undefined}>
            Lender view
          </Link>
        </nav>
        <div className={styles.right}>
          {businesses.length > 0 && (
            <label className={styles.picker}>
              <span className="sr-only">Business</span>
              <select value={business?.id ?? ""} onChange={(e) => setBusinessId(Number(e.target.value))}>
                {businesses.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <span className={styles.status} title={engines.length ? `Free tier: ${engines.join(", ")}` : undefined}>
            <span className={connected ? styles.dotOn : styles.dotOff} aria-hidden />
            {connected ? "Live" : "Offline"}
          </span>
        </div>
      </div>
    </header>
  );
}
