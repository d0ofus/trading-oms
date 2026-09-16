import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Workspace } from "./workspace/Workspace";

const root = document.getElementById("root");

if (root) {
  createRoot(root).render(
    <StrictMode>
      <Workspace />
    </StrictMode>,
  );
}
