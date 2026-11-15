import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Home", end: true },
  { to: "/shop", label: "Shop" },
  { to: "/patterns", label: "Patterns" },
];

export default function NavBar() {
  return (
    <header className="top-nav">
      <div className="brand">
        <span className="brand-badge">C</span>
        Contoso · 12 Patterns
      </div>
      <nav>
        {links.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => (isActive ? "active" : "")}>
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
