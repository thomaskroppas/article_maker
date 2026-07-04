import { marked } from "marked";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

export default function Result() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.result(id).then(setData).catch((e) => setErr(e.message));
  }, [id]);

  if (err) return <div className="card err">Результат недоступен: {err}</div>;
  if (!data) return <div className="card">Загрузка…</div>;

  const qa = data.qa_result || {};
  const fp = data.final_package || {};
  const cls = qa.status === "pass" ? "pass" : qa.status === "fail" ? "fail" : "warn";

  return (
    <>
      <div className="topbar">
        <h1>{fp.meta_title || "Результат"}</h1>
        <span className={`badge ${cls}`}>
          QA {qa.status} — {qa.score}
        </span>
      </div>

      <div className="card">
        <h3>Метаданные</h3>
        <p>
          <b>slug:</b> {fp.slug}
        </p>
        <p>
          <b>meta_description:</b> {fp.meta_description}
        </p>
        <p>
          <b>теги:</b> {(fp.tags || []).join(", ")}
        </p>
      </div>

      {qa.warnings && (
        <div className="card">
          <h3>Предупреждения QA</h3>
          {["critical", "medium", "minor"].map((lvl) => (
            <div key={lvl}>
              <b>{lvl}:</b>
              <ul>
                {(qa.warnings[lvl] || []).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>Статья</h3>
        <div
          className="markdown"
          dangerouslySetInnerHTML={{ __html: marked.parse(data.article_markdown || "") }}
        />
      </div>
    </>
  );
}
