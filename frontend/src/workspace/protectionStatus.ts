import type { ProtectionVerification } from "./api";

export function protectionStatus(
  verification: ProtectionVerification,
  local = false,
) {
  switch (verification.state) {
    case "active":
      return {
        label: local ? "Local protection active" : "Broker stop active",
        tone: "success",
      };
    case "checking":
      return {
        label: local
          ? "Checking local protection"
          : "Checking broker protection",
        tone: "neutral",
      };
    case "exit_pending":
      return { label: "Exit in progress", tone: "neutral" };
    case "closed":
      return { label: "Position closed", tone: "neutral" };
    default:
      return { label: "Protection requires attention", tone: "danger" };
  }
}
