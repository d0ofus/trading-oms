import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";

function renderedText() {
  return renderToStaticMarkup(<App />)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

describe("App", () => {
  it("renders the read-only operations shell sections", () => {
    const text = renderedText();

    expect(text).toContain("Trading OMS");
    expect(text).toContain("Signals");
    expect(text).toContain("Approval tickets");
    expect(text).toContain("Orders");
    expect(text).toContain("Positions");
    expect(text).toContain("Audit events");
    expect(text).toContain("Alerts");
  });

  it("renders the safety posture visibly", () => {
    const text = renderedText();

    expect(text).toContain("Paper mode");
    expect(text).toContain("Live trading disabled");
    expect(text).toContain("Broker connectivity none");
    expect(text).toContain("Manual approval required");
    expect(text).toContain("Append-only journal");
    expect(text).toContain("Alert delivery local-noop");
  });

  it("does not render live-action affordances", () => {
    const html = renderToStaticMarkup(<App />).toLowerCase();
    const forbiddenPhrases = [
      "submit order",
      "place order",
      "transmit order",
      "connect broker",
      "enable live trading",
      "send telegram",
      "add credential",
      "ibkr connect",
    ];

    for (const phrase of forbiddenPhrases) {
      expect(html).not.toContain(phrase);
    }
    expect(html).not.toContain("<button");
    expect(html).not.toContain("<form");
  });
});
