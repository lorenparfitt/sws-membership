import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, money, refusalText, type Quote } from "../api";
import { useBasket } from "../basket";

// Review the basket as the API prices it, then make an order of it. Nothing
// is created until Pay by card; the order page then collects the payment.
export function Checkout() {
  const basket = useBasket();
  const navigate = useNavigate();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    if (basket.ids.length === 0) {
      setQuote(null);
      return;
    }
    api
      .quote(basket.ids)
      .then((q) => {
        setQuote(q);
        setProblem(null);
      })
      .catch((error) => setProblem(refusalText(error, "The basket could not be priced.")));
  }, [basket.ids]);

  async function pay() {
    setPlacing(true);
    setProblem(null);
    try {
      const order = await api.placeOrder(basket.ids);
      basket.clear();
      navigate(`/orders/${order.id}`, { state: { checkout: order.checkout } });
    } catch (error) {
      setProblem(refusalText(error, "Could not start the purchase."));
      setPlacing(false);
    }
  }

  if (basket.ids.length === 0) {
    return (
      <section className="card narrow">
        <h2>Checkout</h2>
        <p>
          Your basket is empty. <Link to="/">Choose passes</Link>
        </p>
      </section>
    );
  }
  if (!quote) return <p>{problem ?? "Pricing your basket…"}</p>;

  const refused = Object.entries(quote.refused);
  const byName = new Map(quote.lines.map((l) => [l.product_name, l]));
  const idOf = (name: string) => byName.get(name)?.product_id;

  return (
    <section className="card narrow">
      <h2>Checkout</h2>
      {refused.length > 0 && (
        <div className="banner problem-banner">
          <p>These items cannot be bought today. Remove them to continue.</p>
          <ul className="reasons">
            {refused.map(([name, reasons]) => (
              <li key={name}>
                <strong>{name}</strong>: {reasons.join("; ")}{" "}
                <button className="link" onClick={() => void removeByName(name)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <table>
        <tbody>
          {quote.lines.map((line) => (
            <tr key={line.product_id}>
              <td>{line.product_name}</td>
              <td className="num">{money(line.amount_cents, quote.currency)}</td>
              <td>
                <button className="link" onClick={() => basket.remove(line.product_id)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
          <tr>
            <th>Total</th>
            <th className="num">{money(quote.total_cents, quote.currency)}</th>
            <th></th>
          </tr>
        </tbody>
      </table>
      {problem && <p className="problem">{problem}</p>}
      <p className="label">A receipt goes to your email once the payment is confirmed.</p>
      <p className="actions">
        <button disabled={placing || refused.length > 0 || quote.lines.length === 0} onClick={() => void pay()}>
          {placing ? "Starting…" : `Pay ${money(quote.total_cents, quote.currency)} by card`}
        </button>
        <Link to="/">Back to the catalog</Link>
      </p>
    </section>
  );

  async function removeByName(name: string) {
    // Refused products are reported by name; find the id from the catalog.
    const id = idOf(name) ?? (await api.catalog(basket.ids)).find((p) => p.name === name)?.id;
    if (id !== undefined) basket.remove(id);
  }
}
