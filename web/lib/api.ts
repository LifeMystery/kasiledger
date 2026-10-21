export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Item = { name: string; quantity: number; unit_price: number | null };
export type Flag = { code: string; message: string };

export type Transaction = {
  id: number;
  business_id: number;
  type: "sale" | "purchase" | "expense" | "repayment";
  items: Item[];
  total: number;
  note: string;
  source: "voice" | "text" | "invoice" | "seed";
  raw_text: string;
  status: "pending" | "confirmed" | "flagged" | "discarded";
  flags: Flag[];
  extractor: string;
  on_credit: boolean;
  credit_confirmed: boolean;
  customer: string | null;
  created_at: string;
};

export type Business = {
  id: number;
  name: string;
  owner_name: string;
  business_type: string;
  location: string;
  address: string;
  channel: string;
  created_at: string;
};

export type DaySummary = {
  date: string;
  sales_count: number;
  revenue: number;
  estimated_profit: number;
  expenses: number;
  stock_bought: number;
  credit_given: number;
  repaid: number;
  top_items: { name: string; quantity: number }[];
  flagged: number;
};

export type TrustComponent = { key: string; label: string; points: number; max: number; detail: string };
export type Trust = {
  score: number;
  level: "High" | "Medium" | "Low";
  estimated_monthly_revenue: number;
  period_days: number;
  revenue_in_period: number;
  components: TrustComponent[];
  flags: { transaction_id: number; total: number; created_at: string; raw_text: string; reasons: string[] }[];
};

export type Analytics = {
  daily: { date: string; sales: number; card_qr: number }[];
  monthly: { month: string; sales: number; purchases: number; expenses: number }[];
  top_items: { name: string; quantity: number; revenue: number }[];
  stock: { name: string; units: number }[];
  outstanding_credit: { customer: string; amount: number; confirmed_amount: number; confirmed: boolean }[];
};

export type ChatMessage = {
  id: number;
  address: string;
  direction: "in" | "out";
  text: string;
  kind: "text" | "voice" | "image" | "document";
  media_url: string;
  created_at: string;
};

export type AppConfig = {
  extractor: string;
  speech: string;
  ocr: string;
  channels: { simulator: boolean; telegram: boolean; whatsapp: boolean };
  tier: string;
};

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json();
}

export async function postForm(path: string, form: FormData): Promise<Response> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res;
}

export function rand(v: number, decimals = 0): string {
  const fixed = v.toLocaleString("en-ZA", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return `R${fixed}`;
}

export function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" });
}
