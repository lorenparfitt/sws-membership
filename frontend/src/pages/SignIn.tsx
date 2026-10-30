import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";

export function SignIn() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .redeem(token)
      .then(() => refresh())
      .then(() => navigate("/", { replace: true }))
      .catch((error: unknown) => {
        setProblem(
          error instanceof ApiError && error.status === 400
            ? "That sign-in link has been used or has expired. Request a new one."
            : "Something went wrong signing you in.",
        );
      });
  }, [token, navigate, refresh]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    await api.requestLink(email);
    setSent(true);
  }

  if (token && !problem) return <p>Signing you in…</p>;

  return (
    <section className="card narrow">
      <h2>Sign in</h2>
      {problem && <p className="problem">{problem}</p>}
      {sent ? (
        <p>
          If <strong>{email}</strong> belongs to a member, a sign-in link is on its way. It works once and
          expires in 15 minutes.
        </p>
      ) : (
        <form onSubmit={submit}>
          <label>
            Email address
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button type="submit">Email me a sign-in link</button>
        </form>
      )}
    </section>
  );
}
