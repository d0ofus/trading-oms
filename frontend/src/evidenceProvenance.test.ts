import { describe, expect, it } from "vitest";

import {
  OPERATIONS_PROVENANCE_RESOURCES,
  createReadApiClient,
  loadOperationsSnapshot,
  safeFallbackOperationsSnapshot,
} from "./readApiClient";

describe("evidence provenance", () => {
  it("labels every safe fallback resource as local and externally unverified", () => {
    expect(Object.keys(safeFallbackOperationsSnapshot.provenance).sort()).toEqual(
      [...OPERATIONS_PROVENANCE_RESOURCES].sort(),
    );

    for (const provenance of Object.values(safeFallbackOperationsSnapshot.provenance)) {
      expect(provenance.broker_derived).toBe(false);
      expect(provenance.externally_verified).toBe(false);
      expect(provenance.classifications).toContain("local_only");
      expect(provenance.classifications).toContain("externally_unverified");
    }

    expect(
      safeFallbackOperationsSnapshot.provenance.paper_trading.classifications,
    ).toEqual(
      expect.arrayContaining(["representative", "demo", "test_double", "adapter_only"]),
    );
    expect(safeFallbackOperationsSnapshot.provenance.paper_trading.summary).toContain(
      "not an authenticated IBKR paper session",
    );
  });

  it("fails closed when an API response claims broker or external provenance", async () => {
    const client = createReadApiClient({
      fetchImpl: async () =>
        new Response(
          JSON.stringify({
            schema_version: 1,
            resource: "safety",
            provenance: {
              schema_version: 1,
              resource: "safety",
              source: "unsafe_source",
              classifications: ["local_only", "externally_unverified"],
              broker_derived: true,
              externally_verified: true,
              summary: "Unsafe provenance claim",
            },
            data: {},
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });

    const state = await loadOperationsSnapshot(client);

    expect(state.status).toBe("error");
    expect(state.snapshot).toBe(safeFallbackOperationsSnapshot);
    expect(state.errorMessage).toContain("showing safe local fallback");
  });
});
