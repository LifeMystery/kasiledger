"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { API_URL, ChatMessage, getJSON, postForm, time } from "@/lib/api";
import { LiveEvent } from "@/lib/live";
import { useLive } from "./BusinessContext";
import styles from "./Phone.module.css";

type Props = {
  phone: string;
  contactName: string;
  quickReplies: { label: string; text: string }[];
  showTools?: boolean;
};

/** Render WhatsApp-style *bold* and line breaks. */
function Formatted({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <Fragment key={i}>
          {line.split(/(\*[^*]+\*)/g).map((part, j) =>
            part.startsWith("*") && part.endsWith("*") && part.length > 2 ? (
              <strong key={j}>{part.slice(1, -1)}</strong>
            ) : (
              <Fragment key={j}>{part}</Fragment>
            ),
          )}
          {i < lines.length - 1 && <br />}
        </Fragment>
      ))}
    </>
  );
}

export default function Phone({ phone, contactName, quickReplies, showTools = true }: Props) {
  const address = `sim:${phone}`;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMessages([]);
    getJSON<ChatMessage[]>(`/api/messages?address=${encodeURIComponent(address)}`)
      .then(setMessages)
      .catch(() => setError("Couldn't load messages from the API."));
  }, [address]);

  useLive(
    useCallback(
      (e: LiveEvent) => {
        if (e.type === "message" && e.message.address === address) {
          setMessages((m) => (m.some((x) => x.id === e.message.id) ? m : [...m, e.message]));
        }
      },
      [address],
    ),
  );

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string, file?: Blob, filename?: string) {
    if (!text.trim() && !file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("phone", phone);
    form.append("text", text);
    if (file) form.append("file", file, filename ?? "upload");
    try {
      await postForm("/api/simulator/send", form);
      setDraft("");
    } catch {
      setError("Message not sent. Check that the API is running.");
    } finally {
      setBusy(false);
    }
  }

  async function sendSampleSlip() {
    const res = await fetch(`${API_URL}/api/simulator/demo-receipt.png`);
    await send("", await res.blob(), "till-slip.png");
  }

  async function toggleRecording() {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (ev) => chunks.push(ev.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        send("", new Blob(chunks, { type: rec.mimeType || "audio/webm" }), "voice-note.webm");
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
    } catch {
      setError("Microphone not available. Allow microphone access in the browser.");
    }
  }

  return (
    <div className={styles.phone}>
      <div className={styles.header}>
        <div className={styles.avatar} aria-hidden>
          K
        </div>
        <div>
          <div className={styles.contact}>KasiLedger</div>
          <div className={styles.sub}>
            {contactName} ({phone})
          </div>
        </div>
      </div>

      <div className={styles.chat} ref={scroller} aria-live="polite">
        {messages.length === 0 && (
          <p className={styles.empty}>Send a message to start. Try one of the suggestions below.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.direction === "in" ? styles.mine : styles.theirs}>
            {m.kind === "image" && m.media_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={`${API_URL}${m.media_url}`} alt="Photo sent" className={styles.photo} />
            )}
            {m.kind === "voice" && m.media_url && (
              <audio controls src={`${API_URL}${m.media_url}`} className={styles.audio} />
            )}
            {m.kind === "document" && m.media_url ? (
              <a className={styles.doc} href={`${API_URL}${m.media_url}`} target="_blank" rel="noreferrer">
                <span aria-hidden>📄</span> <Formatted text={m.text} />
                <span className={styles.docHint}>Open PDF</span>
              </a>
            ) : (
              m.text && <Formatted text={m.text} />
            )}
            <span className={styles.time}>{time(m.created_at)}</span>
          </div>
        ))}
      </div>

      <div className={styles.quick} role="group" aria-label="Suggested messages">
        {quickReplies.map((q) => (
          <button key={q.label} type="button" onClick={() => send(q.text)} disabled={busy} title={q.text}>
            {q.label}
          </button>
        ))}
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <form
        className={styles.compose}
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        {showTools && (
          <>
            <button type="button" className={styles.tool} onClick={() => fileInput.current?.click()} title="Send a photo of a till slip" aria-label="Send a photo">
              📷
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) send("", f, f.name);
                e.target.value = "";
              }}
            />
          </>
        )}
        <input
          className={styles.input}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message"
          aria-label="Message"
        />
        {draft.trim() ? (
          <button type="submit" className={styles.send} disabled={busy} aria-label="Send">
            ➤
          </button>
        ) : (
          <button
            type="button"
            className={recording ? styles.recording : styles.send}
            onClick={toggleRecording}
            aria-label={recording ? "Stop and send voice note" : "Record a voice note"}
            title={recording ? "Tap to send" : "Record a voice note"}
          >
            {recording ? "■" : "🎤"}
          </button>
        )}
      </form>
      {showTools && (
        <button type="button" className={styles.slip} onClick={sendSampleSlip} disabled={busy}>
          Send a sample supplier slip
        </button>
      )}
    </div>
  );
}
