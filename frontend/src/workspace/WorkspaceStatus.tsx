import { useEffect, useState } from "react";
import { exchangeTime, localTime, type Snapshot } from "./api";

export function WorkspaceClock() {
  const [clock, setClock] = useState(new Date().toISOString());
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden) setClock(new Date().toISOString());
    }, 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div>
      <span>Exchange: {exchangeTime(clock)}</span>{" "}
      <span>Local: {localTime(clock)}</span>
    </div>
  );
}

const loadedFrontend = new URL(import.meta.url).pathname.split("/").at(-1);
export function WorkspaceBuild({ build }: { build: Snapshot["build"] }) {
  if (!build) return null;
  const mismatch =
    build.frontend &&
    loadedFrontend?.endsWith(".js") &&
    loadedFrontend !== build.frontend;
  const frontendLabel =
    loadedFrontend?.match(/^index-(.+)\.js$/)?.[1] ?? "development";
  return (
    <div className="ws-inline-actions" role={mismatch ? "alert" : undefined}>
      <small>
        UI {frontendLabel} · Backend {build.backend.slice(0, 8)}
      </small>
      {mismatch && (
        <>
          <span>
            A different application build is running. Reload this tab before
            reviewing new actions.
          </span>
          <button onClick={() => window.location.reload()}>
            Reload application
          </button>
        </>
      )}
    </div>
  );
}
