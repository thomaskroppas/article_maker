import { useEffect, useRef, useState } from "react";
import { api, wsUrl } from "./api";

export const STEP_LABELS = [
  "SERP-анализ",
  "Анализ конкурентов",
  "LSI-ключи",
  "Формирование ТЗ",
  "Структура (outline)",
  "Секции",
  "Сборка markdown",
  "Картинки",
  "FAQ",
  "Вплетение источников",
  "Fact-checking",
  "Финальный QA",
  "Метаданные",
];

// Подписка на пайплайн: история (GET /events) + живой WS, дедуп по event_id.
// Восстановление после F5 обеспечивается тем, что при монтировании всегда
// сначала грузится полная история.
export function usePipeline(articleId) {
  const [events, setEvents] = useState([]);
  const seen = useRef(new Set());
  const wsRef = useRef(null);

  useEffect(() => {
    if (!articleId) return;
    seen.current = new Set();
    setEvents([]);
    let closed = false;

    const add = (list) => {
      const fresh = [];
      for (const e of list) {
        if (e && e.event_id != null && !seen.current.has(e.event_id)) {
          seen.current.add(e.event_id);
          fresh.push(e);
        }
      }
      if (fresh.length) {
        setEvents((prev) =>
          [...prev, ...fresh].sort((a, b) => a.event_id - b.event_id)
        );
      }
    };

    // 1) история (восстановление после reload)
    api
      .events(articleId)
      .then((d) => add(d.events || []))
      .catch(() => {});

    // 2) живой поток
    const ws = new WebSocket(wsUrl(articleId));
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      try {
        add([JSON.parse(msg.data)]);
      } catch (_) {}
    };
    ws.onopen = () => {
      // ping для проверки живости
      try {
        ws.send(JSON.stringify({ type: "ping" }));
      } catch (_) {}
    };

    return () => {
      closed = true;
      try {
        ws.close();
      } catch (_) {}
    };
  }, [articleId]);

  return deriveState(events);
}

function deriveState(events) {
  const steps = STEP_LABELS.map((label, i) => ({
    number: i + 1,
    label,
    status: "pending",
  }));
  let cost = null;
  let review = null;
  let finished = null;
  let aborted = null;
  let currentStep = 0;
  const logs = [];
  const prompts = [];
  const sections = {};

  for (const e of events) {
    const d = e.data || {};
    switch (e.type) {
      case "step_started":
        if (d.step_number) {
          steps[d.step_number - 1].status = "running";
          currentStep = d.step_number;
        }
        review = null; // новый шаг после ревью — панель закрываем
        break;
      case "step_finished":
        if (d.step_number) steps[d.step_number - 1].status = "done";
        break;
      case "cost_update":
        cost = d;
        break;
      case "log_entry":
        logs.push(d);
        break;
      case "prompt_captured":
        prompts.push(d);
        break;
      case "section_update":
        sections[d.section_id] = d;
        break;
      case "review_ready":
        review = d;
        break;
      case "finished":
        finished = d;
        break;
      case "error":
        aborted = { reason: "error", message: d.message };
        break;
      case "aborted":
        aborted = d;
        break;
      default:
        break;
    }
  }

  const lastId = events.length ? events[events.length - 1].event_id : 0;
  return { events, steps, currentStep, cost, review, finished, aborted, logs, prompts, sections, lastId };
}
