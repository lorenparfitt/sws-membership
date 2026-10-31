import { Fragment, useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, money, type MemberDetail as Detail, type StaffProfileBody } from "../api";
import { useAuth } from "../auth";
import { statusLabel } from "./Orders";

function toBody(detail: Detail): StaffProfileBody {
  const p = detail.profile;
  return {
    first_name: p.first_name,
    last_name: p.last_name,
    email: p.email,
    phone: p.phone ?? "",
    date_of_birth: p.date_of_birth,
    address_line_1: p.address_line_1 ?? "",
    address_line_2: p.address_line_2 ?? "",
    city: p.city ?? "",
    province: p.province ?? "BC",
    postal_code: p.postal_code ?? "",
    sports: p.sports,
  };
}

export function MemberDetail() {
  const { memberId } = useParams();
  const id = Number(memberId);
  const { me } = useAuth();
  const isAdmin = me?.roles.includes("admin") ?? false;
  const [detail, setDetail] = useState<Detail | null>(null);
  const [form, setForm] = useState<StaffProfileBody | null>(null);
  const [sports, setSports] = useState<{ value: string; label: string }[]>([]);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [receipt, setReceipt] = useState<{ id: number; text: string } | null>(null);

  const load = useCallback(async () => {
    const d = await api.memberDetail(id);
    setDetail(d);
    setForm(toBody(d));
  }, [id]);

  useEffect(() => {
    load().catch(() => setNote({ ok: false, text: "Member not found." }));
    api.sports().then(setSports);
  }, [load]);

  if (!detail || !form) return <p>{note?.text ?? "Loading…"}</p>;

  const field = (name: keyof StaffProfileBody) => (event: ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [name]: event.target.value });

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setNote(null);
    try {
      const d = await api.staffUpdateProfile(id, { ...form!, date_of_birth: form!.date_of_birth || null });
      setDetail(d);
      setForm(toBody(d));
      setNote({ ok: true, text: "Saved." });
    } catch (error) {
      setNote({ ok: false, text: error instanceof ApiError ? String(error.detail) : "Could not save." });
    }
  }

  function collectCard(orderId: number, totalCents: number) {
    const popup = window.open(`/pay/${orderId}`, `pay-${orderId}`, "popup,width=520,height=720");
    if (!popup) setNote({ ok: false, text: "The browser blocked the payment window. Allow popups for this site." });
    const watch = setInterval(async () => {
      const latest = await api.staffOrderStatus(orderId).catch(() => null);
      if (latest && latest.status !== "pending_payment") {
        clearInterval(watch);
        await load();
        if (latest.status === "paid") setNote({ ok: true, text: `Order ${orderId} paid by card, ${money(totalCents)}.` });
      }
    }, 3000);
    setNote({ ok: true, text: `Order ${orderId} waiting for the card, ${money(totalCents)}.` });
  }

  async function cancelOrder(orderId: number) {
    if (!window.confirm(`Cancel order ${orderId}? Nothing has been charged.`)) return;
    setNote(null);
    try {
      await api.staffCancelOrder(orderId);
      await load();
      setNote({ ok: true, text: `Order ${orderId} cancelled.` });
    } catch (error) {
      setNote({ ok: false, text: error instanceof ApiError ? String(error.detail) : "Could not cancel." });
    }
  }

  async function showReceipt(orderId: number) {
    if (receipt?.id === orderId) return setReceipt(null);
    const text = await api.staffReceipt(orderId).catch(() => "The receipt could not be loaded.");
    setReceipt({ id: orderId, text });
  }

  async function sell(productId: number, method: "cash" | "free" | "card") {
    setNote(null);
    try {
      const order = await api.staffOrder(id, [productId], method);
      if (method === "card" && order.checkout) {
        // The processor session goes to the popup through sessionStorage, never the URL.
        sessionStorage.setItem(`checkout:${order.id}`, JSON.stringify(order.checkout));
        collectCard(order.id, order.total_cents);
        return;
      }
      await load();
      setNote({ ok: true, text: `Order ${order.id} ${order.status}, ${money(order.total_cents)} ${method}.` });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const refused = (error.detail as { refused: Record<string, string[]> }).refused;
        setNote({ ok: false, text: Object.values(refused).flat().join(". ") });
      } else {
        setNote({ ok: false, text: "Could not place the order." });
      }
    }
  }

  async function photograph(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await api.uploadMemberPhoto(id, file);
      await load();
      setPhotoVersion((v) => v + 1);
    } catch {
      setNote({ ok: false, text: "Could not save the photo." });
    }
  }

  async function toggleRole(role: string) {
    const roles = detail!.roles.includes(role) ? detail!.roles.filter((r) => r !== role) : [...detail!.roles, role];
    try {
      setDetail(await api.setRoles(id, roles));
    } catch {
      setNote({ ok: false, text: "Could not change roles." });
    }
  }

  async function printCard() {
    const blob = await api.printCards([id]);
    window.open(URL.createObjectURL(blob), "_blank");
  }

  const p = detail.profile;
  return (
    <section className="account wide">
      <p>
        <Link to="/kiosk">Back to kiosk</Link>
      </p>
      <div className="card">
        <div className="photo-row">
          {detail.has_photo ? (
            <img className="photo" src={`/api/staff/members/${id}/photo?v=${photoVersion}`} alt="" />
          ) : (
            <div className="photo placeholder">No photo</div>
          )}
          <div>
            <h2>
              {p.first_name} {p.last_name}
            </h2>
            <p className="label">
              #{detail.member_number} · {p.email} · {p.phone ?? "no phone"}
              {detail.roles.length > 0 && ` · ${detail.roles.join(", ")}`}
            </p>
            <p className={detail.waiver_current ? "ok" : "problem"}>
              {detail.waiver_current
                ? `Waiver signed ${new Date(detail.waiver_signed_at!).toLocaleDateString()}`
                : "Waiver NOT signed for the current version"}
            </p>
            {p.missing.length > 0 && <p className="problem">Profile missing: {p.missing.join(", ")}</p>}
            <div className="actions">
              <label className="file small">
                {detail.has_photo ? "Retake photo" : "Take photo"}
                <input type="file" accept="image/*" capture="user" onChange={(e) => void photograph(e)} />
              </label>
              <button className="secondary" onClick={() => void printCard()}>
                Print card
              </button>
            </div>
          </div>
        </div>
        {note && <p className={note.ok ? "ok" : "problem"}>{note.text}</p>}
      </div>

      <div className="card">
        <h3>Passes</h3>
        {detail.passes.length === 0 ? (
          <p className="label">None.</p>
        ) : (
          <ul className="passes">
            {detail.passes.map((pass) => (
              <li key={pass.id} className={pass.active ? "" : "inactive"}>
                {pass.product_name} · {pass.valid_from} to {pass.valid_to}
                {pass.visits_remaining !== null && ` · ${pass.visits_remaining} visit(s) left`}
                {!pass.active && " · inactive"}
              </li>
            ))}
          </ul>
        )}
        {detail.today.length > 0 && (
          <p className="label">
            Checked in today: {detail.today.map((c) => `${c.station} ${new Date(c.checked_in_at).toLocaleTimeString()}`).join(", ")}
          </p>
        )}
      </div>

      <div className="card">
        <h3>Sell a pass</h3>
        <p className="label">
          Cash taken at the counter, free, or card. Card opens the payment window for the member to
          enter their own card; card details never pass through this screen.
        </p>
        <ul className="sell">
          {detail.catalog.map((product) => (
            <li key={product.id}>
              <span>
                <strong>{product.name}</strong>{" "}
                {product.price ? money(product.price.amount_cents) : <span className="label">no price today</span>}
                {product.locked_because.length > 0 && (
                  <span className="problem"> · {product.locked_because.join("; ")}</span>
                )}
              </span>
              <span className="actions">
                <button disabled={!product.purchasable} onClick={() => void sell(product.id, "cash")}>
                  Cash
                </button>
                <button className="secondary" disabled={!product.purchasable} onClick={() => void sell(product.id, "free")}>
                  Free
                </button>
                <button className="secondary" disabled={!product.purchasable} onClick={() => void sell(product.id, "card")}>
                  Card
                </button>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <form className="card" onSubmit={saveProfile}>
        <h3>Details</h3>
        <div className="two">
          <label>
            First name
            <input required value={form.first_name} onChange={field("first_name")} />
          </label>
          <label>
            Last name
            <input required value={form.last_name} onChange={field("last_name")} />
          </label>
        </div>
        <div className="two">
          <label>
            Email
            <input type="email" required value={form.email} onChange={field("email")} />
          </label>
          <label>
            Phone
            <input value={form.phone} onChange={field("phone")} />
          </label>
        </div>
        <label>
          Date of birth
          <input type="date" value={form.date_of_birth ?? ""} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} />
        </label>
        <label>
          Address
          <input value={form.address_line_1} onChange={field("address_line_1")} />
        </label>
        <label>
          Address line 2
          <input value={form.address_line_2} onChange={field("address_line_2")} />
        </label>
        <div className="two">
          <label>
            City
            <input value={form.city} onChange={field("city")} />
          </label>
          <label>
            Province
            <input value={form.province} onChange={field("province")} />
          </label>
        </div>
        <label>
          Postal code
          <input value={form.postal_code} onChange={field("postal_code")} />
        </label>
        <fieldset>
          <legend>Sports</legend>
          {sports.map((sport) => (
            <label key={sport.value} className="checkbox">
              <input
                type="checkbox"
                checked={form.sports.includes(sport.value)}
                onChange={() =>
                  setForm({
                    ...form,
                    sports: form.sports.includes(sport.value)
                      ? form.sports.filter((s) => s !== sport.value)
                      : [...form.sports, sport.value],
                  })
                }
              />
              {sport.label}
            </label>
          ))}
        </fieldset>
        <button type="submit">Save details</button>
      </form>

      {isAdmin && (
        <div className="card">
          <h3>Roles</h3>
          {["staff", "admin"].map((role) => (
            <label key={role} className="checkbox">
              <input type="checkbox" checked={detail.roles.includes(role)} onChange={() => void toggleRole(role)} />
              {role}
            </label>
          ))}
        </div>
      )}

      <div className="card">
        <h3>Orders</h3>
        {detail.orders.length === 0 ? (
          <p className="label">None.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Items</th>
                <th>Total</th>
                <th>Paid by</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {detail.orders.map((order) => (
                <Fragment key={order.id}>
                  <tr>
                    <td>{new Date(order.created_at).toLocaleString()}</td>
                    <td>{order.lines.map((l) => l.product_name).join(", ")}</td>
                    <td>{money(order.total_cents)}</td>
                    <td>{order.payment_method}</td>
                    <td>{statusLabel(order.status)}</td>
                    <td className="actions">
                      {order.status === "pending_payment" && (
                        <>
                          <button className="link" onClick={() => collectCard(order.id, order.total_cents)}>
                            Collect card
                          </button>
                          <button className="link" onClick={() => void cancelOrder(order.id)}>
                            Cancel
                          </button>
                        </>
                      )}
                      {order.status === "paid" && (
                        <button className="link" onClick={() => void showReceipt(order.id)}>
                          {receipt?.id === order.id ? "Hide receipt" : "Receipt"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {receipt?.id === order.id && (
                    <tr>
                      <td colSpan={6}>
                        <pre className="receipt">{receipt.text}</pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
