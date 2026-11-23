import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "pretendard/dist/web/variable/pretendardvariable.css";
import App from "./App";
import { PRODUCT_NAME, PRODUCT_NAME_KO } from "./brand";
import "./index.css";

document.title = `${PRODUCT_NAME} · ${PRODUCT_NAME_KO}`;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
