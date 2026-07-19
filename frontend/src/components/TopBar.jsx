import { NavLink, useNavigate } from "react-router-dom";

/**
 * Replaces the old global <Nav />, which showed every role's links/sign-in
 * at once regardless of who was logged in. Each protected page now renders
 * its own small header with just what's relevant to that session.
 */
export default function TopBar({ label, links = [], onSignOut }) {
  const navigate = useNavigate();

  function handleSignOut() {
    onSignOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="topbar">
      <div className="topbar-left">
        <span className="topbar-brand">Data Collection Sprint</span>
        {label && <span className="topbar-label">{label}</span>}
      </div>
      <div className="topbar-right">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? "topbar-link active" : "topbar-link")}
          >
            {link.text}
          </NavLink>
        ))}
        <button type="button" className="btn btn-ghost btn-sm" onClick={handleSignOut}>
          Sign out
        </button>
      </div>
    </div>
  );
}
