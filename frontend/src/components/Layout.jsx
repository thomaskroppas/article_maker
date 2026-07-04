import { NavLink, Outlet } from "react-router-dom";
import { clearCreds, getCreds } from "../api";

export default function Layout() {
  const link = ({ isActive }) => (isActive ? "active" : "");
  return (
    <div className="app">
      <nav className="sidebar">
        <h3 style={{ marginTop: 0 }}>SEO Pipeline</h3>
        <NavLink to="/" end className={link}>
          Главная
        </NavLink>
        <NavLink to="/write" className={link}>
          Написание
        </NavLink>
        <NavLink to="/history" className={link}>
          История
        </NavLink>
        {getCreds() && (
          <a
            href="#/login"
            onClick={() => {
              clearCreds();
            }}
            style={{ marginTop: 24 }}
          >
            Выйти
          </a>
        )}
      </nav>
      <div className="main">
        <Outlet />
      </div>
    </div>
  );
}
