import { BrowserRouter, Link, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Account } from "./pages/Account";
import { Catalog } from "./pages/Catalog";
import { Checkout } from "./pages/Checkout";
import { Kiosk } from "./pages/Kiosk";
import { MemberDetail } from "./pages/MemberDetail";
import { Passes } from "./pages/Passes";
import { PayWindow } from "./pages/PayWindow";
import { SignIn } from "./pages/SignIn";
import { Waiver } from "./pages/Waiver";
import "./styles.css";

function Layout() {
  const { me, signOut } = useAuth();
  return (
    <>
      <header>
        <Link to="/" className="brand">
          Squamish Windsports
        </Link>
        <nav>
          {me ? (
            <>
              <Link to="/">Catalog</Link>
              <Link to="/passes">My passes</Link>
              <Link to="/waiver">Waiver</Link>
              {(me.roles.includes("staff") || me.roles.includes("admin")) && <Link to="/kiosk">Kiosk</Link>}
              <Link to="/account">Account</Link>
              <button className="link" onClick={() => void signOut()}>
                Sign out
              </button>
            </>
          ) : (
            <Link to="/sign-in">Sign in</Link>
          )}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}

function RequireMember() {
  const { me, loading } = useAuth();
  if (loading) return <p>Loading…</p>;
  return me ? <Outlet /> : <Navigate to="/sign-in" replace />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/sign-in" element={<SignIn />} />
            <Route element={<RequireMember />}>
              <Route path="/" element={<Catalog />} />
              <Route path="/checkout/:orderId" element={<Checkout />} />
              <Route path="/passes" element={<Passes />} />
              <Route path="/account" element={<Account />} />
              <Route path="/waiver" element={<Waiver />} />
              <Route path="/kiosk" element={<Kiosk />} />
              <Route path="/kiosk/members/:memberId" element={<MemberDetail />} />
              <Route path="/pay/:orderId" element={<PayWindow />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
