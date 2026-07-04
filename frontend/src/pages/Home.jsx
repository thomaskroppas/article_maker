import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const REQUIRED_ELEMENTS = ["faq", "quick_answer", "table", "list", "conclusion", "weaved_sources"];

const DEFAULTS = {
  article_title: "Где находится озеро Байкал",
  main_keyword: "байкал где находится",
  secondary_keywords: "байкал дно, глубина байкала",
  site_domain: "example.net",
  language: "ru",
  geo: "ru",
  intent: "informational",
  article_type: "informational",
  difficulty: "easy",
  style_archetype: "expert_clear",
  length_strategy: "match_top",
  target_word_count: 1200,
  forbidden_words: "",
  required_elements: ["faq", "quick_answer", "conclusion"],
  review_outline: true,
  enable_section_critic: true,
  force_refresh_serp: false,
};

export default function Home() {
  const [f, setF] = useState(DEFAULTS);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const upd = (k) => (e) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  function toInput() {
    const body = {
      article_title: f.article_title,
      main_keyword: f.main_keyword,
      secondary_keywords: f.secondary_keywords.split(",").map((s) => s.trim()).filter(Boolean),
      site_domain: f.site_domain,
      language: f.language,
      geo: f.geo,
      intent: f.intent,
      article_type: f.article_type,
      difficulty: f.difficulty,
      style_archetype: f.style_archetype,
      length_strategy: f.length_strategy,
      forbidden_words: f.forbidden_words.split(",").map((s) => s.trim()).filter(Boolean),
      required_elements: f.required_elements,
      review_outline: f.review_outline,
      enable_section_critic: f.enable_section_critic,
      force_refresh_serp: f.force_refresh_serp,
    };
    if (f.length_strategy === "custom") body.target_word_count = Number(f.target_word_count);
    return body;
  }

  function validate() {
    setErr("");
    if (f.article_title.length < 5) return "Заголовок ≥ 5 символов";
    if (f.main_keyword.length < 2) return "Ключ ≥ 2 символов";
    if (!f.secondary_keywords.trim()) return "Нужен хотя бы один вторичный ключ";
    if (f.length_strategy === "custom" && !f.target_word_count) return "Укажите target_word_count";
    return "";
  }

  function check() {
    const e = validate();
    if (e) setErr(e);
    else setMsg("Данные валидны ✓");
  }

  async function run() {
    const e = validate();
    if (e) return setErr(e);
    try {
      const { article_id } = await api.runPipeline(toInput());
      nav(`/write?id=${article_id}`);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  const toggleElem = (el) => {
    const has = f.required_elements.includes(el);
    setF({
      ...f,
      required_elements: has
        ? f.required_elements.filter((x) => x !== el)
        : [...f.required_elements, el],
    });
  };

  return (
    <>
      <div className="topbar">
        <h1>Создание статьи</h1>
      </div>

      <div className="card">
        <h3>Основные параметры</h3>
        <label>Тема (заголовок)</label>
        <input value={f.article_title} onChange={upd("article_title")} />
        <div className="row">
          <div>
            <label>Главный ключ</label>
            <input value={f.main_keyword} onChange={upd("main_keyword")} />
          </div>
          <div>
            <label>Сайт (домен)</label>
            <input value={f.site_domain} onChange={upd("site_domain")} />
          </div>
        </div>
        <label>Вторичные ключи (через запятую)</label>
        <input value={f.secondary_keywords} onChange={upd("secondary_keywords")} />
      </div>

      <div className="card">
        <h3>Стратегия объёма</h3>
        <div className="checks">
          {["shorter_top", "match_top", "longer_top", "custom"].map((s) => (
            <label key={s}>
              <input type="radio" name="len" checked={f.length_strategy === s} onChange={() => setF({ ...f, length_strategy: s })} />
              {s}
            </label>
          ))}
        </div>
        {f.length_strategy === "custom" && (
          <>
            <label>target_word_count</label>
            <input type="number" value={f.target_word_count} onChange={upd("target_word_count")} />
          </>
        )}
      </div>

      <div className="card">
        <h3>Параметры генерации</h3>
        <div className="row">
          {[
            ["language", ["ru", "en", "de", "it", "es", "fr"]],
            ["intent", ["informational", "how_to"]],
            ["article_type", ["informational", "how_to"]],
            ["difficulty", ["easy", "medium", "hard"]],
            ["style_archetype", ["expert_clear", "friendly_practical", "calm_analytical", "editorial_neutral"]],
          ].map(([k, opts]) => (
            <div key={k}>
              <label>{k}</label>
              <select value={f[k]} onChange={upd(k)}>
                {opts.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            </div>
          ))}
          <div>
            <label>geo</label>
            <input value={f.geo} onChange={upd("geo")} />
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Ограничения и элементы</h3>
        <label>Запрещённые слова (через запятую)</label>
        <input value={f.forbidden_words} onChange={upd("forbidden_words")} />
        <label>Обязательные элементы</label>
        <div className="checks">
          {REQUIRED_ELEMENTS.map((el) => (
            <label key={el}>
              <input type="checkbox" checked={f.required_elements.includes(el)} onChange={() => toggleElem(el)} />
              {el}
            </label>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Настройки пайплайна</h3>
        <div className="checks">
          <label>
            <input type="checkbox" checked={f.review_outline} onChange={upd("review_outline")} /> Пауза для ревью outline
          </label>
          <label>
            <input type="checkbox" checked={f.enable_section_critic} onChange={upd("enable_section_critic")} /> Критик секций
          </label>
          <label>
            <input type="checkbox" checked={f.force_refresh_serp} onChange={upd("force_refresh_serp")} /> Обновить SERP
          </label>
        </div>
      </div>

      {err && <p className="err">{err}</p>}
      {msg && <p style={{ color: "var(--green)" }}>{msg}</p>}
      <div className="inline">
        <button className="secondary" onClick={check}>
          Проверить данные
        </button>
        <button onClick={run}>Запустить пайплайн</button>
      </div>
    </>
  );
}
