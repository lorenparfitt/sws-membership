import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Waiver as WaiverState } from "../api";
import { useAuth } from "../auth";
import { SignaturePad } from "../SignaturePad";

export function Waiver() {
  const { me } = useAuth();
  const [waiver, setWaiver] = useState<WaiverState | null>(null);
  const [name, setName] = useState("");
  const [signature, setSignature] = useState<string | null>(null);
  const [guardianName, setGuardianName] = useState("");
  const [guardianSignature, setGuardianSignature] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.waiver().then(setWaiver);
  }, []);

  useEffect(() => {
    if (me && !name) setName(`${me.first_name} ${me.last_name}`);
  }, [me, name]);

  if (!waiver) return <p>Loading…</p>;
  if (waiver.template_id === null) return <p>No waiver has been published yet.</p>;

  const ready =
    agreed &&
    name.trim() &&
    signature &&
    (!waiver.needs_guardian || (guardianName.trim() && guardianSignature));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || !waiver || !signature) return;
    setSaving(true);
    setProblem(null);
    try {
      const updated = await api.signWaiver({
        template_id: waiver.template_id!,
        signer_name: name,
        signature_png: signature,
        ...(waiver.needs_guardian
          ? { guardian_name: guardianName, guardian_signature_png: guardianSignature! }
          : {}),
      });
      setWaiver(updated);
    } catch (error) {
      setProblem(error instanceof ApiError ? String(error.detail) : "Could not save the signature.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card">
      <h2>{waiver.title}</h2>
      <p className="label">
        Version {waiver.version}. Document hash {waiver.document_hash?.slice(0, 12)}…
      </p>
      {waiver.signed ? (
        <p className="ok">
          Signed on {new Date(waiver.signed_at!).toLocaleString()}. You are good to go.{" "}
          <Link to="/">Back to the catalog</Link>
        </p>
      ) : (
        <p className="problem">Not signed for the current version. Passes that need the waiver stay locked until you sign.</p>
      )}
      <pre className="waiver-text">{waiver.body_text}</pre>

      {!waiver.signed && (
        <form onSubmit={submit}>
          <label>
            Your full legal name
            <input required value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <SignaturePad label="Your signature" onChange={setSignature} />
          {waiver.needs_guardian && (
            <>
              <p className="label">
                You are under 19, or we do not have your date of birth, so a parent or guardian must
                also sign.
              </p>
              <label>
                Parent or guardian full name
                <input
                  required
                  value={guardianName}
                  onChange={(event) => setGuardianName(event.target.value)}
                />
              </label>
              <SignaturePad label="Parent or guardian signature" onChange={setGuardianSignature} />
            </>
          )}
          <label className="checkbox">
            <input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} />
            I have read the document above and agree to it.
          </label>
          {problem && <p className="problem">{problem}</p>}
          <button type="submit" disabled={!ready || saving}>
            {saving ? "Saving…" : "Sign the waiver"}
          </button>
        </form>
      )}
    </section>
  );
}
