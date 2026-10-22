import { useEffect, useRef, useState } from "react";
import { api, type ArmPreview } from "./api";

export function usePageVisible() {
  const [visible, setVisible] = useState(!document.hidden);
  useEffect(() => {
    const changed = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);
  return visible;
}

export function useArmPolling(
  preview: ArmPreview | null,
  setPreview: (value: ArmPreview | null) => void,
  paused: boolean,
) {
  const ids = preview?.runs.map((r) => r.id).join(",") ?? "";
  const profile = preview?.limits.id;
  const version = preview?.limits.version;
  const unattended = preview?.authorization === "unattended_paper_session";
  const [unavailable, setUnavailable] = useState(false);
  const [revision, recheck] = useState(0);
  const cancelPending = useRef<(() => void) | undefined>(undefined);
  useEffect(() => {
    if (!ids || paused) return;
    let stopped = false;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    const cancel = () => {
      stopped = true;
      window.clearTimeout(timer);
      controller?.abort();
    };
    cancelPending.current = cancel;
    async function poll() {
      if (stopped || document.hidden || controller) return;
      const request = new AbortController();
      controller = request;
      try {
        const value = await api<ArmPreview>(
          "/runs/arm-preview",
          "POST",
          {
            ids: ids.split(","),
            profile_id: profile,
            profile_version: version,
            unattended,
          },
          request.signal,
        );
        if (!stopped && !request.signal.aborted) {
          setPreview(value);
          setUnavailable(false);
        }
      } catch {
        if (!stopped && !request.signal.aborted) setUnavailable(true);
      } finally {
        if (controller === request) controller = undefined;
        if (!stopped && !document.hidden)
          timer = window.setTimeout(() => void poll(), 2000);
      }
    }
    function visibility() {
      window.clearTimeout(timer);
      if (document.hidden) controller?.abort();
      else {
        setUnavailable(true);
        void poll();
      }
    }
    document.addEventListener("visibilitychange", visibility);
    void poll();
    return () => {
      cancel();
      if (cancelPending.current === cancel) cancelPending.current = undefined;
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [ids, profile, version, unattended, paused, revision, setPreview]);
  return {
    unavailable,
    recheck: () => recheck((value) => value + 1),
    cancel: () => cancelPending.current?.(),
  };
}
