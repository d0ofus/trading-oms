import { useCallback, useEffect, useState } from "react";
import { preference, readPreference } from "./api";

/** One workspace selection for reviews opened from Desk, Studio or Testing. */
export function useDeskSelection() {
  const [selected, setSelected] = useState<string[]>(() =>
    readPreference("desk.selected", []),
  );
  const [detail, setDetail] = useState<string | null>(() =>
    readPreference("desk.detail", null),
  );
  useEffect(() => {
    preference("desk.selected", selected);
    preference("desk.detail", detail);
  }, [selected, detail]);
  const selectRuns = useCallback(
    (ids: string[], replacedIds?: string[]) => {
      // Persist before any subsequent navigation or asynchronous overview refresh.
      // Preserve a closed inspector; move an already inspected source to its replacement.
      const inspectedIndex = replacedIds?.indexOf(detail ?? "") ?? -1;
      const inspected =
        inspectedIndex >= 0 ? (ids[inspectedIndex] ?? null) : detail;
      preference("desk.selected", ids);
      preference("desk.detail", inspected);
      setSelected(ids);
      setDetail(inspected);
    },
    [detail],
  );
  return { selected, setSelected, detail, setDetail, selectRuns };
}
