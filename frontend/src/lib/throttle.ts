/**
 * 60fps render throttle.
 * Batches updates and flushes once per animation frame.
 * Data can arrive at 10ms-500ms intervals — we render at most 60fps.
 */
export function createThrottledUpdater<T>(
  onFlush: (batch: T[]) => void
): { push: (item: T) => void; destroy: () => void } {
  let buffer: T[] = [];
  let rafId: number | null = null;

  function flush() {
    if (buffer.length > 0) {
      const batch = buffer;
      buffer = [];
      onFlush(batch);
    }
    rafId = requestAnimationFrame(flush);
  }

  // Start the loop
  rafId = requestAnimationFrame(flush);

  return {
    push(item: T) {
      buffer.push(item);
    },
    destroy() {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      buffer = [];
    },
  };
}
