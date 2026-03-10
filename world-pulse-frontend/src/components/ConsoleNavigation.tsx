import { type ReactNode, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "../pages/Dashboard.css";

type DashboardNavItem = {
  label: string;
  path?: string;
  logout?: boolean;
};

const DASHBOARD_NAV_ITEMS: DashboardNavItem[] = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "Predictions", path: "/trend-prediction" },
  { label: "Historical", path: "/historical-trends" },
  { label: "Scenario Studio", path: "/scenario" },
  { label: "About", path: "/about" },
  { label: "Contact", path: "/contact" },
  { label: "Logout", logout: true },
];

type ConsoleNavigationProps = {
  title: ReactNode;
  subtitle: string;
  rightSlot?: ReactNode;
};

export default function ConsoleNavigation({
  title,
  subtitle,
  rightSlot,
}: ConsoleNavigationProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (!navOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setNavOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navOpen]);

  const handleDrawerNavigate = (item: DashboardNavItem) => {
    if (item.logout) {
      setNavOpen(false);
      localStorage.removeItem("token");
      navigate("/login");
      return;
    }

    if (!item.path || item.path === location.pathname) {
      setNavOpen(false);
      return;
    }

    setNavOpen(false);
    navigate(item.path);
  };

  return (
    <>
      <aside id="dashboard-navigation" className={`dashboard-drawer ${navOpen ? "is-open" : ""}`} aria-hidden={!navOpen}>
        <div className="dashboard-drawer__header">
          <div>
            <span className="dashboard-drawer__eyebrow">Navigation</span>
            <strong>World Pulse Console</strong>
          </div>
          <button
            type="button"
            className="dashboard-drawer__close"
            onClick={() => setNavOpen(false)}
            aria-label="Close navigation panel"
          >
            Close
          </button>
        </div>
        <nav className="dashboard-drawer__nav" aria-label="Dashboard navigation">
          {DASHBOARD_NAV_ITEMS.map((item) => (
            <button
              key={item.label}
              type="button"
              className={`dashboard-drawer__link ${item.logout ? "is-logout" : ""} ${item.path === location.pathname ? "is-active" : ""}`}
              onClick={() => handleDrawerNavigate(item)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>
      {navOpen ? <button type="button" className="dashboard-drawer__scrim" onClick={() => setNavOpen(false)} aria-label="Close navigation overlay" /> : null}
      <header className="wp-top wp-top-refined">
        <div className="wp-brand-block">
          <button
            type="button"
            className="wp-burger wp-burger-button"
            onClick={() => setNavOpen((prev) => !prev)}
            aria-label={navOpen ? "Close navigation panel" : "Open navigation panel"}
            aria-expanded={navOpen}
            aria-controls="dashboard-navigation"
          >
            <span />
            <span />
            <span />
          </button>
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
        </div>
        {rightSlot ? <div className="wp-header-meta">{rightSlot}</div> : null}
      </header>
    </>
  );
}
