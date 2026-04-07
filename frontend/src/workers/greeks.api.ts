import { wrap, type Remote } from 'comlink';
import type { GreeksInput, GreeksResult } from './greeks.worker';

export type { GreeksInput, GreeksResult };

let worker: Remote<{
  calculate(input: GreeksInput): GreeksResult;
  batchCalculate(inputs: GreeksInput[]): GreeksResult[];
}> | null = null;

export function getGreeksWorker() {
  if (!worker) {
    const raw = new Worker(new URL('./greeks.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker = wrap(raw);
  }
  return worker;
}
