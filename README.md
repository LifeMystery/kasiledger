# KasiLedger

Voice-first bookkeeping and business verification for informal businesses.
Shop owners record sales, stock, expenses and credit by sending simple messages (or voice notes and
photos of till slips). KasiLedger checks the records against independent evidence and produces a
trust score and a lender-ready PDF report.

Everything here runs **free**. Paid AI services are optional upgrades you switch on in `.env` later.

```
kasiledger/
  backend/   Python FastAPI API: chat flow, parser, OCR, verification, trust score, PDF report
  web/       Next.js dashboard: phone simulator, live counter book, lender view
```

---

## 1. What you need

| Tool | Why | Get it |
|---|---|---|
| Python 3.10+ | the API | python.org |
| Node.js 20+ | the dashboard | nodejs.org |
| Tesseract OCR | reading supplier slips (optional) | Windows: the UB Mannheim installer. Mac: `brew install tesseract`. Linux: `sudo apt install tesseract-ocr` |

## 2. Run the API

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
python -m app.seed            # demo data (deletes the existing database)
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Run the tests: `pytest -q`

## 3. Run the dashboard

```bash
cd web
npm install
cp .env.example .env.local    # Windows: copy .env.example .env.local
npm run dev
```

Open http://localhost:3000

- **Live**: a phone simulator on the left (owner and customer) and the live counter book on the right.
- **Lender view**: trust score, evidence breakdown, 90-day sales chart, flagged entries, PDF report.

## 4. Demo data

`python -m app.seed` creates:

- **Thandi's Spaza** (Orlando East, Soweto), phone `+27820000001`: 90 days of trading, supplier slips,
  card/QR payments, credit confirmed by customers, and one old flagged entry. Trust score in the 90s.
- **Lerato's Hair Studio** (Tembisa), phone `+27820000003`: 3 weeks of records and no payment
  evidence, so a Medium score. Useful to show the contrast.

---

## 5. Messages the owner can send

| What | Example |
|---|---|
| Sale | `sale bread 3 18` (3 loaves at R18) |
| Several items | `sale bread 2 18, milk 1 25` |
| Mixed language | `Ngithengise izinkwa ezimbili ne-cooldrink, R66` |
| Stock bought | `buy bread 40 14.50` or a photo of the till slip |
| Expense | `expense taxi 30`, `paid rent 900` |
| Sale on credit | `owe Sipho 40 0821110001` (the customer is asked to confirm) |
| Customer paid back | `paid Sipho 20` |
| Commands | `summary`, `stock`, `owed`, `score`, `report`, `undo`, `help` |

Every entry is read back and saved only after the owner replies **1** (or yes/yebo/ewe).
**2** discards it.

To add words in more languages, edit `backend/app/ai/lexicon.py`. Have native speakers check the
isiZulu, Sesotho, Setswana and Afrikaans words there.

## 6. How records are verified

| Check | What happens |
|---|---|
| Stock vs sales | A sale bigger than the stock bought (from slips/purchases) is flagged |
| Unusual amount | A sale more than 5× the shop's average sale is flagged |
| Unusual day | A day more than 3× the shop's normal daily takings is flagged |
| Customer confirmation | Credit sales are confirmed or disputed by the customer by message |
| Payment evidence | Imported card/QR statements (CSV) are matched to daily sales |

Trust score (0–100): trading history 20, stock-backed sales 25, card/QR evidence 20,
customer-confirmed credit 15, clean record 20. Flagged entries don't count as verified income.

---

## 7. The 3-minute demo

1. Open **Live** with Thandi's Spaza selected. Introduce Thandi and her problem.
2. Tap **Sale**, then **Save (1)**. The entry lands in the counter book.
3. Tap **isiZulu sale**, then **Save (1)**. Mixed language works.
4. Tap **Send a sample supplier slip**, then **Save (1)**. The slip is read and stock goes up.
5. Tap **Fake big sale**, then **Save (1)**. It is flagged red: not enough stock, and far above the usual sale.
6. Tap **Credit**, then **Save (1)**. Switch to **Customer (Sipho)** and tap **Yes**. Switch back: confirmed.
7. Open **Lender view**: trust score, where it comes from, the flagged entry. Click **Download verified report**.

Before presenting: run `python -m app.seed` for a clean slate, and record a backup video of this flow.

---

## 8. Free upgrades (switch on in `backend/.env`)

### Voice notes (free, local)
```bash
pip install -r requirements-voice.txt
```
Set `SPEECH=local_whisper`. The first voice note downloads the Whisper model (about 150 MB for
`base`). Good for English; weaker for isiZulu/Sesotho, so the owner still confirms each entry.
Voice notes also work from the simulator's microphone button.

### Understanding normal sentences (free, local AI)
Install Ollama (ollama.com), then:
```bash
ollama pull qwen2.5:3b
```
Set `EXTRACTOR=ollama`. If Ollama is slow or unsure, KasiLedger falls back to the keyword parser.

### Telegram (free, real phones, voice notes and photos)
1. In Telegram, message **@BotFather**, send `/newbot`, copy the token.
2. Set `TELEGRAM_BOT_TOKEN=...` in `.env` and restart the API.
3. Message your bot. Polling mode needs no public URL.

Telegram doesn't share phone numbers, so customers confirm credit by sending `CONFIRM 1234`
(the code is given to the owner).

### WhatsApp Cloud API test number (free for development)
1. At developers.facebook.com create an app and add WhatsApp.
2. Copy the temporary access token and phone number ID into `WHATSAPP_TOKEN` and
   `WHATSAPP_PHONE_NUMBER_ID`. Add your own number as a test recipient.
3. Expose the API with a free tunnel (`cloudflared tunnel --url http://localhost:8000` or ngrok) and
   set the webhook URL to `https://<tunnel>/webhooks/whatsapp` with verify token
   `kasiledger-verify`. Subscribe to `messages`.
4. Set `PUBLIC_BASE_URL` to the tunnel URL so report links work.

The temporary token expires after about a day; generate a new one before demo day.

### Daily summaries
Set `DAILY_SUMMARY_TIME=19:00` and every business gets its summary at 7pm.

## 9. Paid upgrades later

Each AI part sits behind a small class, so a paid service is one new class plus one `.env` value:

| Part | Free now | Paid later |
|---|---|---|
| Understanding messages | `RuleBasedExtractor`, `OllamaExtractor` (`app/ai/extractor.py`) | Azure OpenAI / Claude / Gemini |
| Voice notes | `LocalWhisper` (`app/ai/speech.py`) | Azure AI Speech (has isiZulu) |
| Slip reading | `TesseractOcr` (`app/ai/ocr.py`) | Azure AI Document Intelligence |
| Database | SQLite | PostgreSQL / Azure SQL (`DATABASE_URL`) |
| WhatsApp | test number | verified WhatsApp Business number |

## 10. Payment evidence CSV

```
date,amount,provider,reference
2026-10-01 10:15,45.00,Yoco,TXN001
2026-10-01 16:40,120.00,SnapScan,TXN002
```
Import it on the Lender view under **Add payment evidence**.
