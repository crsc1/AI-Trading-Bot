import { api } from '../lib/api';
import {
  setFindings,
  setFindingsLoading,
  setLastFindingsUpdateAt,
  setLastSourcesUpdateAt,
  setModel,
  setSources,
  setSourcesLoading,
} from '../signals/agent';
import type { ResearchFinding, SourcesResponse } from '../types/agent';

let sourcesSubscribers = 0;
let findingsSubscribers = 0;
let sourcesTimer: ReturnType<typeof setInterval> | null = null;
let findingsTimer: ReturnType<typeof setInterval> | null = null;
let sourcesInflight: Promise<void> | null = null;
let findingsInflight: Promise<void> | null = null;

async function refreshSources() {
  if (sourcesInflight) return sourcesInflight;

  setSourcesLoading(true);
  sourcesInflight = (async () => {
    try {
      const data = await api.get<SourcesResponse>('/api/brain/sources');
      setSources(data?.sources || []);
      setModel(data?.model || '');
      setLastSourcesUpdateAt(Date.now());
    } catch (_) {
      // Keep the last good snapshot on failures.
    } finally {
      setSourcesLoading(false);
      sourcesInflight = null;
    }
  })();

  return sourcesInflight;
}

async function refreshFindings() {
  if (findingsInflight) return findingsInflight;

  setFindingsLoading(true);
  findingsInflight = (async () => {
    try {
      const data = await api.get<{ findings: ResearchFinding[] }>('/api/research/findings?limit=10');
      setFindings(data?.findings || []);
      setLastFindingsUpdateAt(Date.now());
    } catch (_) {
      // Keep the last good snapshot on failures.
    } finally {
      setFindingsLoading(false);
      findingsInflight = null;
    }
  })();

  return findingsInflight;
}

export function subscribeAgentSources() {
  sourcesSubscribers += 1;
  if (sourcesSubscribers === 1) {
    void refreshSources();
    sourcesTimer = setInterval(() => {
      void refreshSources();
    }, 15_000);
  }
}

export function unsubscribeAgentSources() {
  sourcesSubscribers = Math.max(0, sourcesSubscribers - 1);
  if (sourcesSubscribers === 0 && sourcesTimer) {
    clearInterval(sourcesTimer);
    sourcesTimer = null;
  }
}

export function subscribeResearchFindings() {
  findingsSubscribers += 1;
  if (findingsSubscribers === 1) {
    void refreshFindings();
    findingsTimer = setInterval(() => {
      void refreshFindings();
    }, 60_000);
  }
}

export function unsubscribeResearchFindings() {
  findingsSubscribers = Math.max(0, findingsSubscribers - 1);
  if (findingsSubscribers === 0 && findingsTimer) {
    clearInterval(findingsTimer);
    findingsTimer = null;
  }
}
