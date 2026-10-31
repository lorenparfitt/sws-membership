import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";

export function SignIn() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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

  async function withPassword(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    try {
      await api.signInWithPassword(email, password);
      await refresh();
      navigate("/", { replace: true });
    } catch (error) {
      setProblem(
        error instanceof ApiError && error.status === 401
          ? "Email or password not recognised. If you have not set a password yet, use the emailed link."
          : "Something went wrong signing you in.",
      );
    }
  }

  async function withLink() {
    setProblem(null);
    if (!email) {
      setProblem("Enter your email address first.");
      return;
    }
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
          expires in 15 minutes. Once in, you can set a password under{" "}
          <Link to="/account">Account</Link>.
        </p>
      ) : (
        <form onSubmit={withPassword}>
          <label>
            Email address
            <input
              type="email"
              required
              autoFocus
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <div className="actions">
            <button type="submit" disabled={!password}>
              Sign in
            </button>
            <button type="button" className="secondary" onClick={() => void withLink()}>
              Email me a sign-in link instead
            </button>
          </div>
          <p className="label">
            No password yet, or forgotten it? The emailed link signs you in, and you can set a new
            password from there.
          </p>
        </form>
      )}
    </section>
  );
}
