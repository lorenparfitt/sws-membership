import { useEffect, useState, type FormEvent } from "react";
import { admin, ApiError, type WaiverHistory } from "../../api";

export function WaiverAdmin() {
  const [history, setHistory] = useState<WaiverHistory | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const load = () => admin.waiverHistory().then(setHistory);
  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const current = history?.templates[0];
    if (current && !title && !body) {
      setTitle(current.title);
      setBody(current.body_text);
    }
  }, [history, title, body]);

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (!window.confirm("Publish a new waiver version? Every member will have to sign again.")) return;
    try {
      const result = await admin.publishWaiver(title, body);
      setNote({ ok: true, text: `Published version ${result.version}.` });
      await load();
    } catch (error) {
      setNote({ ok: false, text: error instanceof ApiError ? String(error.detail) : "Could not publish." });
    }
  }

  async function reset(event: FormEvent) {
    event.preventDefault();
    if (!window.confirm("Reset all signatures? Every member will have to sign the current text again.")) return;
    try {
      await admin.resetWaivers(reason);
      setReason("");
      setNote({ ok: true, text: "Signatures reset." });
      await load();
    } catch (error) {
      setNote({ ok: false, text: error instanceof ApiError ? String(error.detail) : "Could not reset." });
    }
  }

  return (
    <div className="admin">
      {note && <p className={note.ok ? "ok" : "problem"}>{note.text}</p>}
      <form className="card" onSubmit={publish}>
        <h3>Publish a new version</h3>
        <p className="label">
          Publishing makes every existing signature stale. Current version: {history?.templates[0]?.version ?? "none"}.
        </p>
        <label>
          Title
          <input required value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Waiver text
          <textarea required rows={16} value={body} onChange={(e) => setBody(e.target.value)} />
        </label>
        <button type="submit">Publish as version {(history?.templates[0]?.version ?? 0) + 1}</button>
      </form>

      <form className="card" onSubmit={reset}>
        <h3>Reset signatures without changing the text</h3>
        <label>
          Reason, kept on record
          <input required value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button type="submit" className="secondary">
          Reset all signatures
        </button>
      </form>

      <div className="card">
        <h3>History</h3>
        <ul className="admin-list">
          {history?.templates.map((t) => (
            <li key={t.id}>
              Version {t.version}: {t.title}, published {new Date(t.published_at).toLocaleString()}
            </li>
          ))}
          {history?.resets.map((r) => (
            <li key={r.reset_at} className="label">
              Reset {new Date(r.reset_at).toLocaleString()}: {r.reason}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
