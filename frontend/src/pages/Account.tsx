import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";

export function Account() {
  const { me, refresh } = useAuth();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNote(null);
    if (password !== again) {
      setNote({ ok: false, text: "The two entries do not match." });
      return;
    }
    try {
      await api.setPassword(password);
      await refresh();
      setPassword("");
      setAgain("");
      setNote({ ok: true, text: "Password saved. You can sign in with it from now on." });
    } catch (error) {
      setNote({
        ok: false,
        text:
          error instanceof ApiError && error.status === 400
            ? "Passwords need at least 10 characters."
            : "Could not save the password.",
      });
    }
  }

  if (!me) return null;

  return (
    <section className="card narrow">
      <h2>Account</h2>
      <p>
        {me.first_name} {me.last_name}, member number <strong>{me.member_number}</strong>, {me.email}
      </p>
      <h3>{me.has_password ? "Change password" : "Set a password"}</h3>
      <p className="label">
        At least 10 characters. The emailed sign-in link keeps working either way, and is how you
        get back in if you forget this.
      </p>
      <form onSubmit={submit}>
        <label>
          New password
          <input
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label>
          New password again
          <input
            type="password"
            required
            autoComplete="new-password"
            value={again}
            onChange={(event) => setAgain(event.target.value)}
          />
        </label>
        <button type="submit">Save password</button>
      </form>
      {note && <p className={note.ok ? "ok" : "problem"}>{note.text}</p>}
    </section>
  );
}
