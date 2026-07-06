import { safetyPosture } from "./safety";

export function App() {
  return (
    <main>
      <h1>Trading OMS</h1>
      <dl>
        <div>
          <dt>Mode</dt>
          <dd>{safetyPosture.appMode}</dd>
        </div>
        <div>
          <dt>Live trading</dt>
          <dd>{safetyPosture.liveTradingEnabled ? "enabled" : "disabled"}</dd>
        </div>
        <div>
          <dt>Broker connectivity</dt>
          <dd>{safetyPosture.brokerConnectivity}</dd>
        </div>
      </dl>
    </main>
  );
}
