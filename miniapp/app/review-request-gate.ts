export type ReviewRequestIdentity = {
  attemptId: string;
  generation: number;
};

export type ReviewRequestResult<T> =
  | { status: "current"; value: T }
  | { status: "error"; error: unknown }
  | { status: "stale" };

function sameIdentity(
  left: ReviewRequestIdentity | null,
  right: ReviewRequestIdentity,
): boolean {
  return left?.attemptId === right.attemptId && left.generation === right.generation;
}

export function createReviewRequestGate() {
  let activeIdentity: ReviewRequestIdentity | null = null;
  let requestVersion = 0;

  return {
    activate(identity: ReviewRequestIdentity): void {
      activeIdentity = { ...identity };
      requestVersion += 1;
    },

    async run<T>(
      identity: ReviewRequestIdentity,
      request: () => Promise<T>,
    ): Promise<ReviewRequestResult<T>> {
      if (!sameIdentity(activeIdentity, identity)) return { status: "stale" };
      const version = requestVersion + 1;
      requestVersion = version;
      try {
        const value = await request();
        if (version !== requestVersion || !sameIdentity(activeIdentity, identity)) {
          return { status: "stale" };
        }
        return { status: "current", value };
      } catch (error) {
        if (version !== requestVersion || !sameIdentity(activeIdentity, identity)) {
          return { status: "stale" };
        }
        return { status: "error", error };
      }
    },
  };
}
