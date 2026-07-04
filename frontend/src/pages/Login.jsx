import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setCreds } from "../api";

export default function Login() {
  const [user, setUser] = useState("admin");
  const [pass, setPass] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();

  async function submit(e) {
    e.preventDefault();
    setCreds(user, pass);
    try {
      await api.get("/settings"); // проверка авторизации
      nav("/");
    } catch (_) {
      setErr("Неверные логин или пароль");
    }
  }

  return (
    <div className="main" style={{ maxWidth: 380, margin: "80px auto" }}>
      <h1>Вход</h1>
      <form className="card" onSubmit={submit}>
        <label>Логин</label>
        <input value={user} onChange={(e) => setUser(e.target.value)} />
        <label>Пароль</label>
        <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} />
        {err && <p className="err">{err}</p>}
        <button style={{ marginTop: 16 }} type="submit">
          Войти
        </button>
      </form>
    </div>
  );
}
