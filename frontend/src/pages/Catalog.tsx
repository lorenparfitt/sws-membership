import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money, type Product } from "../api";
import { useBasket } from "../basket";

export function Catalog() {
  const basket = useBasket();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  // The catalog is judged with the basket counted as held, so adding the
  // membership unlocks the passes that need it and shows their member price.
  useEffect(() => {
    api.catalog(basket.ids).then(setProducts).catch(() => setProblem("Could not load the catalog."));
  }, [basket.ids]);

  if (!products) return <p>{problem ?? "Loading…"}</p>;

  const chosen = products.filter((p) => basket.has(p.id));
  const subtotal = chosen.reduce((sum, p) => sum + (p.price?.amount_cents ?? 0), 0);

  return (
    <section>
      <h2>Passes and memberships</h2>
      {problem && <p className="problem">{problem}</p>}
      <ul className="products">
        {products.map((product) => {
          const inBasket = basket.has(product.id);
          return (
            <li key={product.id} className={`card ${product.purchasable || inBasket ? "" : "locked"}`}>
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
                      {/membership/i.test(reason) && <span className="label"> Add the membership to your basket first.</span>}
                    </li>
                  ))}
                </ul>
              )}
              {inBasket ? (
                <button className="secondary" onClick={() => basket.remove(product.id)}>
                  Remove from basket
                </button>
              ) : (
                <button disabled={!product.purchasable} onClick={() => basket.add(product.id)}>
                  {product.purchasable ? "Add to basket" : "Not available"}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {chosen.length > 0 && (
        <div className="basket-bar">
          <span>
            <strong>{chosen.length}</strong> {chosen.length === 1 ? "item" : "items"}, {money(subtotal)}
          </span>
          <span className="actions">
            <button className="link" onClick={basket.clear}>
              Empty basket
            </button>
            <Link to="/checkout" className="button">
              Checkout
            </Link>
          </span>
        </div>
      )}
    </section>
  );
}
