import { useEffect, useState } from "react";
import { api, type Incident } from "./api";

/** One visible detail request at a time; no audit replay or payload cache. */
export function useIncidentDetail(identity: string | undefined) {
  const [detail, setDetail] = useState<Incident | null>(null);
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setDetail(null);
  }, [identity]);
  useEffect(() => {
    setAvailable(false);
    setError("");
    if (!identity) return;
    let alive = true;
    let current: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      if (!alive || document.hidden || current) return;
      const controller = new AbortController();
      current = controller;
      setChecking(true);
      try {
        const result = await api<Incident>(
          `/incidents/${identity}`,
          "GET",
          undefined,
          controller.signal,
        );
        if (alive && !controller.signal.aborted) {
          setDetail(result);
          setAvailable(true);
          setError("");
        }
      } catch (failure) {
        if (alive && !controller.signal.aborted) {
          setAvailable(false);
          setError((failure as Error).message);
        }
      } finally {
        if (alive && current === controller) {
          current = undefined;
          setChecking(false);
          if (!document.hidden) timer = setTimeout(() => void load(), 2000);
        }
      }
    }
    function visibility() {
      clearTimeout(timer);
      current?.abort();
      current = undefined;
      setAvailable(false);
      setChecking(false);
      if (!document.hidden) void load();
    }
    document.addEventListener("visibilitychange", visibility);
    void load();
    return () => {
      alive = false;
      current?.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [identity, revision]);
  return {
    detail,
    available,
    error,
    checking,
    recheck: () => setRevision((value) => value + 1),
  };
}
