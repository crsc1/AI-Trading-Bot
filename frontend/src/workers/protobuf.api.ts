/**
 * Protobuf decoder worker wrapper — Comlink proxy for off-thread decoding.
 */
import { wrap, type Remote } from 'comlink';

interface ProtoWorkerAPI {
  decode(buffer: ArrayBuffer): any;
  decodeBatch(buffers: ArrayBuffer[]): any[];
}

let worker: Remote<ProtoWorkerAPI> | null = null;

export function getProtoWorker(): Remote<ProtoWorkerAPI> {
  if (!worker) {
    const raw = new Worker(new URL('./protobuf.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker = wrap<ProtoWorkerAPI>(raw);
  }
  return worker;
}
