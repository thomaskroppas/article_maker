import { useEffect, useState } from "react";

// T-1: пустая оболочка с тёмной темой + индикатор связи с backend.
// Экраны (Главная, Написание, Review, Результат, История) — T-13.
export default function App() {
  const [health, setHealth] = useState("…");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => setHealth(`ok (v${d.version})`))
      .catch(() => setHealth("недоступен"));
  }, []);

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "48px 24px" }}>
      <h1 style={{ color: "var(--mauve)", marginBottom: 8 }}>SEO Pipeline</h1>
      <p style={{ color: "var(--subtext)", marginTop: 0 }}>
        Веб-версия. Каркас (T-1). Экраны появятся в T-13.
      </p>
      <p style={{ color: "var(--subtext)" }}>
        Backend:{" "}
        <span
          style={{
            color: health.startsWith("ok") ? "var(--green)" : "var(--red)",
          }}
        >
          {health}
        </span>
      </p>
    </div>
  );
}
