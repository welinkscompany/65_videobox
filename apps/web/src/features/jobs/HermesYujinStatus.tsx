import { useCallback, useEffect, useRef, useState } from "react";

import { api, type HermesYujinStatus as HermesYujinStatusDto } from "../../api";
import { Button } from "../../components/ui/button";

const statusCopy: Record<HermesYujinStatusDto["state"], string> = {
  not_configured: "유진 연결이 아직 준비되지 않았어요.",
  stopped: "유진과 연결할 수 없어요.",
  starting: "유진 연결을 준비하고 있어요.",
  http_ready: "유진 연결은 됐지만 대화 확인은 아직이에요.",
  provider_ready: "유진이 답변을 준비하고 있어요.",
  chat_verified: "유진과 대화할 준비가 확인됐어요.",
  degraded: "최근에는 유진과 대화가 원활하지 않았어요.",
};

export function HermesYujinStatus() {
  const [status, setStatus] = useState<HermesYujinStatusDto | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(false);
  const inFlightRef = useRef(false);
  const requestEpochRef = useRef(0);
  const latestCheckedAtRef = useRef(Number.NEGATIVE_INFINITY);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    const epoch = ++requestEpochRef.current;
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    try {
      const next = await api.getHermesYujinStatus(controller.signal);
      if (!mountedRef.current || epoch !== requestEpochRef.current) return;
      const checkedAt = Date.parse(next.checked_at);
      if (checkedAt >= latestCheckedAtRef.current) {
        latestCheckedAtRef.current = checkedAt;
        setStatus(next);
        setFailed(false);
      }
    } catch (error) {
      if (
        mountedRef.current
        && epoch === requestEpochRef.current
        && !(error instanceof Error && error.name === "AbortError")
      ) {
        setFailed(true);
      }
    } finally {
      if (epoch === requestEpochRef.current) {
        inFlightRef.current = false;
        controllerRef.current = null;
        if (mountedRef.current) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    return () => {
      mountedRef.current = false;
      requestEpochRef.current += 1;
      inFlightRef.current = false;
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [load]);

  return <section aria-label="유진 연결 상태">
    <h2>유진 연결 상태</h2>
    {status ? <p role="status">{statusCopy[status.state]}</p> : null}
    {failed ? <p role="alert">유진 연결 상태를 확인하지 못했어요. 유진 없이도 편집을 계속할 수 있어요.</p> : null}
    <Button type="button" variant="outline" disabled={loading} onClick={() => void load()}>
      다시 확인
    </Button>
  </section>;
}
