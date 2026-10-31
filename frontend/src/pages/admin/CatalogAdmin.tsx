import { useEffect, useState, type FormEvent } from "react";
import { admin, ApiError, money, type AdminProduct, type CatalogOptions } from "../../api";

function Problem({ text }: { text: string | null }) {
  return text ? <p className="problem">{text}</p> : null;
}

function describe(error: unknown): string {
  return error instanceof ApiError ? String(error.detail) : "Request failed.";
}

export function CatalogAdmin() {
  const [products, setProducts] = useState<AdminProduct[]>([]);
  const [options, setOptions] = useState<CatalogOptions | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [newProduct, setNewProduct] = useState({ name: "", description: "", season_year: new Date().getFullYear(), sort_order: 0 });
  const [rollover, setRollover] = useState({ from_year: new Date().getFullYear(), to_year: new Date().getFullYear() + 1 });

  async function load() {
    setProducts(await admin.products());
  }
  useEffect(() => {
    load().catch(() => setProblem("Could not load the catalog."));
    admin.options().then(setOptions);
  }, []);

  function replace(updated: AdminProduct) {
    setProducts((all) => all.map((p) => (p.id === updated.id ? updated : p)));
  }

  async function act(work: () => Promise<AdminProduct | AdminProduct[] | void>) {
    setProblem(null);
    try {
      const result = await work();
      if (Array.isArray(result)) await load();
      else if (result) replace(result);
    } catch (error) {
      setProblem(describe(error));
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    try {
      const created = await admin.createProduct({ ...newProduct, active: false });
      setProducts((all) => [created, ...all]);
      setOpen(created.id);
      setNewProduct({ ...newProduct, name: "", description: "" });
    } catch (error) {
      setProblem(describe(error));
    }
  }

  const seasons = [...new Set(products.map((p) => p.season_year))].sort((a, b) => b - a);

  return (
    <div className="admin">
      <Problem text={problem} />
      <form className="card row" onSubmit={create}>
        <h3>New product</h3>
        <input required placeholder="Name, e.g. Adult Season Pass 2027" value={newProduct.name} onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })} />
        <input placeholder="Description" value={newProduct.description} onChange={(e) => setNewProduct({ ...newProduct, description: e.target.value })} />
        <label>
          Season <input type="number" value={newProduct.season_year} onChange={(e) => setNewProduct({ ...newProduct, season_year: Number(e.target.value) })} />
        </label>
        <label>
          Order <input type="number" value={newProduct.sort_order} onChange={(e) => setNewProduct({ ...newProduct, sort_order: Number(e.target.value) })} />
        </label>
        <button type="submit">Create (inactive)</button>
      </form>

      <form
        className="card row"
        onSubmit={(e) => {
          e.preventDefault();
          void act(() => admin.rollover(rollover.from_year, rollover.to_year));
        }}
      >
        <h3>Roll a season forward</h3>
        <label>
          From <input type="number" value={rollover.from_year} onChange={(e) => setRollover({ ...rollover, from_year: Number(e.target.value) })} />
        </label>
        <label>
          To <input type="number" value={rollover.to_year} onChange={(e) => setRollover({ ...rollover, to_year: Number(e.target.value) })} />
        </label>
        <button type="submit" className="secondary">
          Copy products as inactive drafts
        </button>
      </form>

      {seasons.map((season) => (
        <div key={season}>
          <h3>Season {season}</h3>
          {products
            .filter((p) => p.season_year === season)
            .map((product) => (
              <ProductCard key={product.id} product={product} options={options} open={open === product.id} onToggle={() => setOpen(open === product.id ? null : product.id)} act={act} />
            ))}
        </div>
      ))}
    </div>
  );
}

function ProductCard({
  product,
  options,
  open,
  onToggle,
  act,
}: {
  product: AdminProduct;
  options: CatalogOptions | null;
  open: boolean;
  onToggle: () => void;
  act: (work: () => Promise<AdminProduct | void>) => Promise<void>;
}) {
  const [edit, setEdit] = useState({ name: product.name, description: product.description, sort_order: product.sort_order, active: product.active, season_year: product.season_year });
  const [price, setPrice] = useState({ label: "Regular", amount: "", starts_at: `${product.season_year}-01-01`, ends_at: `${product.season_year}-12-31`, members_only: false });
  const [grant, setGrant] = useState({ kind: "membership", valid_from: `${product.season_year}-01-01`, valid_to: `${product.season_year}-12-31`, visit_count: "" });
  const [rule, setRule] = useState({ kind: "requires_current_waiver", parameters: {} as Record<string, string>, failure_message: "" });

  useEffect(() => {
    setEdit({ name: product.name, description: product.description, sort_order: product.sort_order, active: product.active, season_year: product.season_year });
  }, [product]);

  const ruleSpec = options?.rule_kinds.find((r) => r.kind === rule.kind);

  return (
    <div className={`card product-admin ${product.active ? "" : "locked"}`}>
      <div className="product-head" onClick={onToggle}>
        <strong>{product.name}</strong>
        <span className="label">
          {product.active ? "on sale" : "inactive"} · {product.prices.length} price(s) · {product.grants.length} grant(s) · {product.rules.length} rule(s)
        </span>
      </div>
      {open && (
        <div className="product-body">
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              void act(() => admin.updateProduct(product.id, edit));
            }}
          >
            <input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
            <input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
            <label>
              Order <input type="number" value={edit.sort_order} onChange={(e) => setEdit({ ...edit, sort_order: Number(e.target.value) })} />
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} /> On sale
            </label>
            <button type="submit">Save</button>
          </form>

          <h4>Prices</h4>
          <ul className="admin-list">
            {product.prices.map((p) => (
              <li key={p.id}>
                {p.label || "price"} {money(p.amount_cents)} · {p.starts_at} to {p.ends_at ?? "open"}
                {p.members_only && " · members only"}
                <button className="link" onClick={() => void act(() => admin.removePrice(product.id, p.id))}>
                  remove
                </button>
              </li>
            ))}
          </ul>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              void act(() =>
                admin.addPrice(product.id, {
                  label: price.label,
                  amount_cents: Math.round(Number(price.amount) * 100),
                  starts_at: price.starts_at,
                  ends_at: price.ends_at || null,
                  members_only: price.members_only,
                }),
              );
            }}
          >
            <input placeholder="Label" value={price.label} onChange={(e) => setPrice({ ...price, label: e.target.value })} />
            <input required type="number" step="0.01" min="0" placeholder="Amount CAD" value={price.amount} onChange={(e) => setPrice({ ...price, amount: e.target.value })} />
            <input type="date" value={price.starts_at} onChange={(e) => setPrice({ ...price, starts_at: e.target.value })} />
            <input type="date" value={price.ends_at} onChange={(e) => setPrice({ ...price, ends_at: e.target.value })} />
            <label className="checkbox">
              <input type="checkbox" checked={price.members_only} onChange={(e) => setPrice({ ...price, members_only: e.target.checked })} /> Members only
            </label>
            <button type="submit" className="secondary">
              Add price
            </button>
          </form>

          <h4>Grants (what buying it confers)</h4>
          <ul className="admin-list">
            {product.grants.map((g) => (
              <li key={g.id}>
                {g.kind} · {g.valid_from} to {g.valid_to}
                {g.visit_count !== null && ` · ${g.visit_count} visit(s)`}
                <button className="link" onClick={() => void act(() => admin.removeGrant(product.id, g.id))}>
                  remove
                </button>
              </li>
            ))}
          </ul>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              void act(() =>
                admin.addGrant(product.id, {
                  kind: grant.kind,
                  valid_from: grant.valid_from,
                  valid_to: grant.valid_to,
                  visit_count: grant.visit_count ? Number(grant.visit_count) : null,
                }),
              );
            }}
          >
            <select value={grant.kind} onChange={(e) => setGrant({ ...grant, kind: e.target.value })}>
              {options?.entitlement_kinds.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <input type="date" value={grant.valid_from} onChange={(e) => setGrant({ ...grant, valid_from: e.target.value })} />
            <input type="date" value={grant.valid_to} onChange={(e) => setGrant({ ...grant, valid_to: e.target.value })} />
            <input type="number" min="1" placeholder="Visits (for visit passes)" value={grant.visit_count} onChange={(e) => setGrant({ ...grant, visit_count: e.target.value })} />
            <button type="submit" className="secondary">
              Add grant
            </button>
          </form>

          <h4>Rules (who may buy it)</h4>
          <ul className="admin-list">
            {product.rules.map((r) => (
              <li key={r.id}>
                <strong>{r.kind}</strong> {Object.keys(r.parameters).length > 0 && JSON.stringify(r.parameters)} · "{r.failure_message}"
                <button className="link" onClick={() => void act(() => admin.removeRule(product.id, r.id))}>
                  remove
                </button>
              </li>
            ))}
          </ul>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault();
              void act(() => admin.addRule(product.id, rule));
            }}
          >
            <select value={rule.kind} onChange={(e) => setRule({ kind: e.target.value, parameters: {}, failure_message: rule.failure_message })}>
              {options?.rule_kinds.map((r) => (
                <option key={r.kind} value={r.kind}>
                  {r.kind}
                </option>
              ))}
            </select>
            {ruleSpec &&
              Object.entries(ruleSpec.parameters).map(([name, help]) =>
                name === "kind" ? (
                  <select key={name} value={rule.parameters.kind ?? ""} onChange={(e) => setRule({ ...rule, parameters: { ...rule.parameters, kind: e.target.value } })}>
                    <option value="">entitlement kind…</option>
                    {options?.entitlement_kinds.map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input key={name} placeholder={help} value={rule.parameters[name] ?? ""} onChange={(e) => setRule({ ...rule, parameters: { ...rule.parameters, [name]: e.target.value } })} />
                ),
              )}
            <input required placeholder="Message shown when it fails" value={rule.failure_message} onChange={(e) => setRule({ ...rule, failure_message: e.target.value })} />
            <button type="submit" className="secondary">
              Add rule
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
