import { NavLink, Outlet } from "react-router-dom";

export function AdminLayout() {
  return (
    <section>
      <nav className="tabs">
        <NavLink to="/admin/catalog">Catalog</NavLink>
        <NavLink to="/admin/waiver">Waiver</NavLink>
        <NavLink to="/admin/reports">Reports</NavLink>
      </nav>
      <Outlet />
    </section>
  );
}
