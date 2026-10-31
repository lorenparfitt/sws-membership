import { BrowserRouter, Link, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Account } from "./pages/Account";
import { Catalog } from "./pages/Catalog";
import { Checkout } from "./pages/Checkout";
import { Passes } from "./pages/Passes";
import { SignIn } from "./pages/SignIn";
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
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
