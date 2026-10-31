import { Fragment, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money, type Order } from "../api";

export function statusLabel(status: string): string {
  return { pending_payment: "Awaiting payment", paid: "Paid", cancelled: "Cancelled", refunded: "Refunded" }[status] ?? status;
}

export function Orders() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [receipt, setReceipt] = useState<{ id: number; text: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(() => api.orders().then(setOrders).catch(() => setProblem("Orders could not be loaded.")), []);

  useEffect(() => {
    void load();
  }, [load]);

  async function cancel(id: number) {
    if (!window.confirm("Cancel this order? Nothing has been charged.")) return;
    await api.cancelOrder(id).catch(() => setProblem("The order could not be cancelled."));
    await load();
  }

  async function showReceipt(id: number) {
    if (receipt?.id === id) return setReceipt(null);
    const text = await api.receipt(id).catch(() => "The receipt could not be loaded.");
    setReceipt({ id, text });
  }

  if (!orders) return <p>{problem ?? "Loading…"}</p>;
  const pending = orders.filter((o) => o.status === "pending_payment");
  const settled = orders.filter((o) => o.status !== "pending_payment");

  return (
    <section>
      <h2>Orders</h2>
      {problem && <p className="problem">{problem}</p>}

      {pending.length > 0 && (
        <div className="card">
          <h3>Awaiting payment</h3>
          <ul className="sell">
            {pending.map((order) => (
              <li key={order.id}>
                <span>
                  {order.lines.map((l) => l.product_name).join(", ")} <strong>{money(order.total_cents, order.currency)}</strong>
                  <br />
                  <span className="label">Started {new Date(order.created_at).toLocaleString()}</span>
                </span>
                <span className="actions">
                  <Link to={`/orders/${order.id}`}>Continue to payment</Link>
                  <button className="link" onClick={() => void cancel(order.id)}>
                    Cancel
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {settled.length === 0 ? (
        <p className="label">No orders yet.</p>
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
            {settled.map((order) => (
              <Fragment key={order.id}>
                <tr>
                  <td>{new Date(order.paid_at ?? order.created_at).toLocaleDateString()}</td>
                  <td>{order.lines.map((l) => l.product_name).join(", ")}</td>
                  <td>{money(order.total_cents, order.currency)}</td>
                  <td>{order.payment_method}</td>
                  <td>{statusLabel(order.status)}</td>
                  <td>
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
    </section>
  );
}
