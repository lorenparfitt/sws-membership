import { useEffect, useState, type FormEvent } from "react";
import { admin, ApiError, type ReportInfo, type ReportOutput } from "../../api";

export function ReportsAdmin() {
  const [reports, setReports] = useState<ReportInfo[]>([]);
  const [chosen, setChosen] = useState<ReportInfo | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [output, setOutput] = useState<ReportOutput | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    admin.reports().then(setReports);
  }, []);

  function choose(report: ReportInfo) {
    setChosen(report);
    setOutput(null);
    setParams(Object.fromEntries(report.parameters.map((p) => [p.name, String(p.default ?? "")])));
  }

  async function run(event: FormEvent) {
    event.preventDefault();
    if (!chosen) return;
    setProblem(null);
    try {
      setOutput(await admin.runReport(chosen.name, params));
    } catch (error) {
      setProblem(error instanceof ApiError ? String(error.detail) : "The report failed.");
    }
  }

  async function download() {
    if (!chosen) return;
    const blob = await admin.reportCsv(chosen.name, params);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${chosen.name}.csv`;
    link.click();
  }

  return (
    <div className="admin reports">
      <ul className="card report-list">
        {reports.map((r) => (
          <li key={r.name} className={chosen?.name === r.name ? "chosen" : ""} onClick={() => choose(r)}>
            <strong>{r.title}</strong>
            <span className="label">{r.description}</span>
          </li>
        ))}
      </ul>
      <div>
        {chosen && (
          <form className="card row" onSubmit={run}>
            <h3>{chosen.title}</h3>
            {chosen.parameters.map((p) => (
              <label key={p.name}>
                {p.label}
                <input
                  type={p.kind === "date" ? "date" : p.kind === "int" ? "number" : "text"}
                  value={params[p.name] ?? ""}
                  onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                />
              </label>
            ))}
            <button type="submit">Run</button>
            {output && (
              <button type="button" className="secondary" onClick={() => void download()}>
                Download CSV
              </button>
            )}
          </form>
        )}
        {problem && <p className="problem">{problem}</p>}
        {output && (
          <div className="card">
            <p className="label">{output.rows.length} row(s)</p>
            <table>
              <thead>
                <tr>
                  {output.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {output.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{String(cell ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
