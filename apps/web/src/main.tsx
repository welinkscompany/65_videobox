import ReactDOM from "react-dom/client";

import { installNetworkGuard } from "./lib/network-guard";

import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import "./styles/index.css";

installNetworkGuard();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
