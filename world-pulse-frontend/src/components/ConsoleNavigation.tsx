import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "../pages/Dashboard.css";

type DashboardNavItem = {
  label: string;
  path?: string;
  logout?: boolean;
};

const BASE_DASHBOARD_NAV_ITEMS: DashboardNavItem[] = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "Profile", path: "/profile" },
  { label: "Predictions", path: "/trend-prediction" },
  { label: "Historical", path: "/historical-trends" },
  { label: "Scenario Studio", path: "/scenario" },
  { label: "Response Console", path: "/response-console" },
  { label: "About", path: "/about" },
  { label: "Contact", path: "/contact" },
  { label: "Logout", logout: true },
];

type ConsoleNavigationProps = {
  title: ReactNode;
  subtitle: string;
  rightSlot?: ReactNode;
  sectionTabs?: Array<{
    label: string;
    targetId: string;
    badge?: string;
  }>;
};

export default function ConsoleNavigation({
  title,
  subtitle,
  rightSlot,
  sectionTabs = [],
}: ConsoleNavigationProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const isAdminUser = localStorage.getItem("role") === "admin";

  const navItems = useMemo(() => {
    if (!isAdminUser) return BASE_DASHBOARD_NAV_ITEMS;

    const withAdmin = [...BASE_DASHBOARD_NAV_ITEMS];
    withAdmin.splice(
      5,
      0,
      { label: "Admin", path: "/admin" },
      { label: "System Monitor", path: "/admin/system-monitoring" },
      { label: "Security Logs", path: "/admin/security-logs" },
    );
    return withAdmin;
  }, [isAdminUser]);

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
      localStorage.removeItem("role");
      localStorage.removeItem("user_type");
      localStorage.removeItem("name");
      localStorage.removeItem("email");
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

  const handleSectionTabClick = (targetId: string) => {
    const element = document.getElementById(targetId);
    if (!element) return;
    element.scrollIntoView({ behavior: "smooth", block: "start" });
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
          {navItems.map((item) => (
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
      {sectionTabs.length ? (
        <div className="console-section-tabs" role="navigation" aria-label="Page sections">
          {sectionTabs.map((tab) => (
            <button
              key={tab.targetId}
              type="button"
              className="console-section-tab"
              onClick={() => handleSectionTabClick(tab.targetId)}
            >
              {tab.label}
              {tab.badge ? <span className="console-section-tab-badge">{tab.badge}</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </>
  );
}
