import { useState } from "react";

type ReadinessIdentity = { readiness_id: string; revision: number } | null | undefined;
type Confirmation = { readinessKey: string | null; confirmed: boolean };

function readinessKey(readiness: ReadinessIdentity) {
  return readiness ? `${readiness.readiness_id}:${readiness.revision}` : null;
}

export function usePlaceholderConfirmation(readiness: ReadinessIdentity) {
  const currentReadinessKey = readinessKey(readiness);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  if (confirmation?.readinessKey !== currentReadinessKey) {
    setConfirmation({ readinessKey: currentReadinessKey, confirmed: false });
  }
  const confirmed = confirmation?.readinessKey === currentReadinessKey && confirmation.confirmed;

  return {
    confirmed,
    setConfirmed(next: boolean) {
      setConfirmation({ readinessKey: currentReadinessKey, confirmed: next });
    },
  };
}
