import { createStore } from 'solid-js/store';
import type { MarketLevelsResponse } from '../lib/api';

interface ResourceState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastUpdatedAt: number | null;
}

interface ReferenceState {
  symbol: string | null;
  expiration: string | null;
  chainReady: boolean;
  chainLoading: boolean;
  chainError: string | null;
  volatility: ResourceState<any>;
  snapshot: ResourceState<any>;
  gex: ResourceState<any>;
  sectors: ResourceState<any>;
  levels: ResourceState<MarketLevelsResponse>;
}

function resourceState<T>(): ResourceState<T> {
  return {
    data: null,
    loading: true,
    error: null,
    lastUpdatedAt: null,
  };
}

const [reference, setReference] = createStore<ReferenceState>({
  symbol: null,
  expiration: null,
  chainReady: false,
  chainLoading: true,
  chainError: null,
  volatility: resourceState<any>(),
  snapshot: resourceState<any>(),
  gex: resourceState<any>(),
  sectors: resourceState<any>(),
  levels: resourceState<MarketLevelsResponse>(),
});

export { reference, setReference };

function emptyResourceState<T>(): ResourceState<T> {
  return {
    data: null,
    loading: true,
    error: null,
    lastUpdatedAt: null,
  };
}

export function setReferenceSymbol(symbol: string | null) {
  setReference('symbol', symbol);
}

export function setReferenceExpiration(expiration: string | null) {
  setReference('expiration', expiration);
}

export function setChainStatus(loading: boolean, ready: boolean, error: string | null = null) {
  setReference('chainLoading', loading);
  setReference('chainReady', ready);
  setReference('chainError', error);
}

export function setReferenceResource<K extends keyof Pick<ReferenceState, 'volatility' | 'snapshot' | 'gex' | 'sectors' | 'levels'>>(
  key: K,
  patch: Partial<ResourceState<ReferenceState[K]['data']>>
) {
  setReference(key, (prev) => ({ ...prev, ...patch }));
}

export function resetReferenceForSymbol(symbol: string) {
  setReference({
    symbol,
    expiration: null,
    chainReady: false,
    chainLoading: true,
    chainError: null,
    volatility: emptyResourceState<any>(),
    snapshot: emptyResourceState<any>(),
    gex: reference.gex,
    sectors: reference.sectors,
    levels: emptyResourceState<MarketLevelsResponse>(),
  });
}
