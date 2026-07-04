import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { STEP_LABELS, usePipeline } from "../usePipeline";

export default function Write() {
  const [params] = useSearchParams();
  const id = params.get("id");
  const p = usePipeline(id);
  const [tab, setTab] = useState("log");

  if (!id)
    return (
      <div className="card">
        Нет активной генерации. Начните на <Link to="/">Главной</Link> или укажите{" "}
        <code>?id=</code>.
      </div>
    );

  const hero = p.aborted
    ? { text: `Прервано: ${p.aborted.reason}`, cls: "fail" }
    : p.finished
    ? { text: "Готово", cls: "pass" }
    : p.review
    ? { text: "Пауза: ревью структуры", cls: "warn" }
    : p.currentStep
    ? { text: `Шаг ${p.currentStep}/13 — ${STEP_LABELS[p.currentStep - 1]}`, cls: "" }
    : { text: "Ожидание…", cls: "" };

  return (
    <>
      <div className="topbar">
        <h1>Написание</h1>
        <div className="inline">
          {p.cost && <span className="badge">$ {p.cost.article}</span>}
          {!p.finished && !p.aborted && (
            <button className="danger" onClick={() => api.stop(id)}>
              Стоп
            </button>
          )}
        </div>
      </div>

      <div className="card">
        <h2 style={{ margin: 0 }}>
          <span className={`badge ${hero.cls}`}>{hero.text}</span>
        </h2>
      </div>

      {p.review && <ReviewPanel id={id} review={p.review} />}

      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="card" style={{ flex: "0 0 280px" }}>
          <h3>Шаги</h3>
          <ul className="steps">
            {p.steps.map((s) => (
              <li key={s.number} className={s.status}>
                <span className="dot" />
                {s.number}. {s.label}
              </li>
            ))}
          </ul>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <div className="tabs">
            {[
              ["log", "Лог"],
              ["prompts", "Диалог агентов"],
              ["result", "Результат"],
            ].map(([k, l]) => (
              <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
                {l}
              </button>
            ))}
          </div>

          {tab === "log" && (
            <div className="log">
              {p.logs.length === 0 && <div style={{ color: "var(--subtext)" }}>Пока пусто…</div>}
              {p.logs.map((l, i) => (
                <div key={i} className={l.level}>
                  [{l.level}] {l.message}
                </div>
              ))}
            </div>
          )}

          {tab === "prompts" && (
            <div className="log">
              {p.prompts.length === 0 && (
                <div style={{ color: "var(--subtext)" }}>Промпты появятся при живом прогоне.</div>
              )}
              {p.prompts.map((pr, i) => (
                <details key={i}>
                  <summary>{pr.step_name}</summary>
                  <pre>{pr.prompt}</pre>
                  <pre style={{ color: "var(--green)" }}>{pr.response}</pre>
                </details>
              ))}
            </div>
          )}

          {tab === "result" &&
            (p.finished ? (
              <div>
                <p>
                  QA:{" "}
                  <span className={`badge ${qaCls(p.finished.qa_result?.status)}`}>
                    {p.finished.qa_result?.status} — {p.finished.qa_result?.score}
                  </span>
                </p>
                <Link to={`/result/${id}`}>Открыть результат →</Link>
              </div>
            ) : (
              <div style={{ color: "var(--subtext)" }}>Результат появится по завершении.</div>
            ))}
        </div>
      </div>
    </>
  );
}

function qaCls(status) {
  if (status === "pass") return "pass";
  if (status === "fail") return "fail";
  return "warn";
}

function ReviewPanel({ id, review }) {
  const [h1, setH1] = useState(review.outline?.h1 || "");
  const [json, setJson] = useState(JSON.stringify(review.outline, null, 2));
  const [err, setErr] = useState("");
  const [sent, setSent] = useState(false);
  const startedAt = useMemo(() => Date.now(), []);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [startedAt]);

  async function resume() {
    setErr("");
    let outline;
    try {
      outline = JSON.parse(json);
      outline.h1 = h1;
    } catch (e) {
      return setErr("Некорректный JSON outline");
    }
    try {
      await api.resume(id, outline);
      setSent(true);
    } catch (e) {
      setErr(e.message);
    }
  }

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="card" style={{ borderColor: "var(--yellow)" }}>
      <div className="topbar">
        <h3 style={{ margin: 0 }}>Ревью структуры</h3>
        <span className="badge warn">на паузе: {mm}:{ss}</span>
      </div>
      <p style={{ color: "var(--subtext)" }}>
        Точек роста (после дедупа): {review.content_gaps_filtered?.length ?? 0}
      </p>
      <label>H1</label>
      <input value={h1} onChange={(e) => setH1(e.target.value)} />
      <label>Outline (JSON, редактируемый)</label>
      <textarea rows={12} value={json} onChange={(e) => setJson(e.target.value)} />
      {err && <p className="err">{err}</p>}
      <div style={{ marginTop: 12 }}>
        <button onClick={resume} disabled={sent}>
          {sent ? "Отправлено…" : "Подтвердить и продолжить"}
        </button>
      </div>
    </div>
  );
}
