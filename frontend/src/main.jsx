import React from "react";
import ReactDOM from "react-dom/client";
import { createHashRouter, Navigate, RouterProvider } from "react-router-dom";
import { getCreds } from "./api";
import Layout from "./components/Layout.jsx";
import History from "./pages/History.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import Result from "./pages/Result.jsx";
import Write from "./pages/Write.jsx";
import "./index.css";

function Guard({ children }) {
  return getCreds() ? children : <Navigate to="/login" replace />;
}

const router = createHashRouter([
  { path: "/login", element: <Login /> },
  {
    path: "/",
    element: (
      <Guard>
        <Layout />
      </Guard>
    ),
    children: [
      { index: true, element: <Home /> },
      { path: "write", element: <Write /> },
      { path: "history", element: <History /> },
      { path: "result/:id", element: <Result /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
