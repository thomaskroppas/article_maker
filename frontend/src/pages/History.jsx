import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function History() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");

  const load = () => api.articles().then(setRows).catch((e) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);

  async function del(id) {
    if (!confirm("Удалить статью и её файлы?")) return;
    await api.del(`/articles/${id}`);
    load();
  }

  return (
    <>
      <div className="topbar">
        <h1>История</h1>
      </div>
      {err && <p className="err">{err}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Заголовок</th>
              <th>Статус</th>
              <th>QA</th>
              <th>Стоимость</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.article_id}>
                <td>{a.title || a.main_keyword || a.article_id.slice(0, 8)}</td>
                <td>{a.status}</td>
                <td>{a.qa_score ?? "—"}</td>
                <td>{a.cost_usd != null ? `$${a.cost_usd}` : "—"}</td>
                <td>
                  <Link to={`/result/${a.article_id}`}>результат</Link> ·{" "}
                  <Link to={`/write?id=${a.article_id}`}>лог</Link> ·{" "}
                  <a href="#" className="err" onClick={() => del(a.article_id)}>
                    удалить
                  </a>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ color: "var(--subtext)" }}>
                  Пока нет статей.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
