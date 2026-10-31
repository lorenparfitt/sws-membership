import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, type CheckInResult, type GateMember } from "../api";

type Station = "spit" | "shuttle";

export function Kiosk() {
  const [query, setQuery] = useState("");
  const [station, setStation] = useState<Station>("spit");
  const [results, setResults] = useState<GateMember[] | null>(null);
  const [last, setLast] = useState<CheckInResult | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const refreshCounts = useCallback(() => api.kioskToday().then(setCounts).catch(() => undefined), []);

  useEffect(() => {
    void refreshCounts();
    input.current?.focus();
  }, [refreshCounts]);

  async function search(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setLast(null);
    try {
      const found = await api.kioskLookup(query);
      setResults(found);
      // A scanner types the number and presses Enter: one exact hit checks in at once.
      if (found.length === 1 && /^\D*\d+\D*$/.test(query)) await admit(found[0]);
    } catch {
      setProblem("Lookup failed.");
    } finally {
      setQuery("");
      input.current?.focus();
    }
  }

  async function admit(member: GateMember) {
    try {
      const result = await api.kioskCheckIn(member.id, station);
      setLast(result);
      setResults([result.member]);
      void refreshCounts();
    } catch {
      setProblem("Check-in failed.");
    }
  }

  return (
    <section>
      <div className="kiosk-head">
        <h2>Kiosk</h2>
        <div className="counts">
          Today: Spit <strong>{counts.spit ?? 0}</strong>, Shuttle <strong>{counts.shuttle ?? 0}</strong>
        </div>
      </div>
      <form onSubmit={search} className="kiosk-search">
        <input
          ref={input}
          placeholder="Scan a card, or type a member number, email or name"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
        <select value={station} onChange={(event) => setStation(event.target.value as Station)}>
          <option value="spit">Spit</option>
          <option value="shuttle">Shuttle</option>
        </select>
        <button type="submit">Find</button>
      </form>
      {problem && <p className="problem">{problem}</p>}
      {last && (
        <p className={last.admitted ? (last.new_today ? "ok banner" : "banner") : "problem banner"}>
          {last.admitted ? (last.new_today ? "Admitted: " : "Already in: ") : "Refused: "}
          {last.member.first_name} {last.member.last_name}, {last.message}
        </p>
      )}
      {results && results.length === 0 && <p>Nobody matches.</p>}
      {results && results.length > 0 && (
        <ul className="products">
          {results.map((member) => (
            <li key={member.id} className="card">
              <h3>
                {member.first_name} {member.last_name}
              </h3>
              <p className="label">
                #{member.member_number} · {member.email}
                {member.date_of_birth && ` · born ${member.date_of_birth}`}
              </p>
              <p className={member.waiver_current ? "ok" : "problem"}>
                {member.waiver_current ? "Waiver signed" : "Waiver NOT signed for the current version"}
              </p>
              <ul className="passes">
                {member.passes.length === 0 && <li className="label">No passes</li>}
                {member.passes.map((pass) => (
                  <li key={pass.id} className={pass.active ? "" : "inactive"}>
                    {pass.product_name}
                    {pass.visits_remaining !== null && ` · ${pass.visits_remaining} visit(s) left`}
                    {!pass.active && " · inactive"}
                  </li>
                ))}
              </ul>
              {member.today.length > 0 && (
                <p className="label">
                  Today: {member.today.map((c) => `${c.station} at ${new Date(c.checked_in_at).toLocaleTimeString()}`).join(", ")}
                </p>
              )}
              <button onClick={() => void admit(member)}>Check in at {station}</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
