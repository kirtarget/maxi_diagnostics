import { describe, expect, it } from "vitest";

import { createReviewRequestGate } from "./review-request-gate";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((fulfill) => { resolve = fulfill; });
  return { promise, resolve };
}

describe("review request gate", () => {
  it("discards attempt A when its deferred response resolves after attempt B", async () => {
    const gate = createReviewRequestGate();
    const attemptA = { attemptId: "attempt-a", generation: 1 };
    const attemptB = { attemptId: "attempt-b", generation: 2 };
    const responseA = deferred<string>();
    const responseB = deferred<string>();

    gate.activate(attemptA);
    const pendingA = gate.run(attemptA, () => responseA.promise);
    gate.activate(attemptB);
    const pendingB = gate.run(attemptB, () => responseB.promise);

    responseB.resolve("review-b");
    await expect(pendingB).resolves.toEqual({ status: "current", value: "review-b" });

    responseA.resolve("review-a");
    await expect(pendingA).resolves.toEqual({ status: "stale" });
  });
});
