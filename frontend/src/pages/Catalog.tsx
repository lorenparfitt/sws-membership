import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, money, type Product } from "../api";

export function Catalog() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [buying, setBuying] = useState<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.catalog().then(setProducts).catch(() => setProblem("Could not load the catalog."));
  }, []);

  async function buy(product: Product) {
    setBuying(product.id);
    setProblem(null);
    try {
      const order = await api.placeOrder([product.id]);
      navigate(`/checkout/${order.id}`, { state: { checkout: order.checkout } });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const refused = (error.detail as { refused: Record<string, string[]> }).refused;
        setProblem(Object.values(refused).flat().join(". "));
      } else {
        setProblem("Could not start the purchase.");
      }
    } finally {
      setBuying(null);
    }
  }

  if (!products) return <p>{problem ?? "Loading…"}</p>;

  return (
    <section>
      <h2>Passes and memberships</h2>
      {problem && <p className="problem">{problem}</p>}
      <ul className="products">
        {products.map((product) => (
          <li key={product.id} className={`card ${product.purchasable ? "" : "locked"}`}>
            <h3>{product.name}</h3>
            <p>{product.description}</p>
            <p className="price">
              {product.price ? (
                <>
                  {money(product.price.amount_cents, product.price.currency)}
                  <span className="label"> {product.price.label}</span>
                  {product.price.ends_at && <span className="label"> until {product.price.ends_at}</span>}
                </>
              ) : (
                <span className="label">No price available to you today</span>
              )}
            </p>
            {product.locked_because.length > 0 && (
              <ul className="reasons">
                {product.locked_because.map((reason) => (
                  <li key={reason}>
                    {reason}
                    {/waiver/i.test(reason) && (
                      <>
                        {" "}
                        <Link to="/waiver">Sign it</Link>
                      </>
                    )}
                    {/profile/i.test(reason) && (
                      <>
                        {" "}
                        <Link to="/account">Go to Account</Link>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <button disabled={!product.purchasable || buying !== null} onClick={() => buy(product)}>
              {buying === product.id ? "Starting…" : product.purchasable ? "Buy" : "Not available"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
