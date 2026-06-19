import { useEffect, useState } from "react";
import { Home } from "./pages/Home";
import { TaskDetail } from "./pages/TaskDetail";

function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export function App() {
  const hash = useHashRoute();
  const match = hash.match(/^#\/task\/(.+)$/);
  return (
    <div className="app">
      <header className="topbar">
        <a href="#/" className="brand">🔥 Mini-Drop</a>
        <span className="sub">性能采集与火焰图平台</span>
      </header>
      <main>{match ? <TaskDetail tid={match[1]} /> : <Home />}</main>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge b-${status}`}>{status}</span>;
}
