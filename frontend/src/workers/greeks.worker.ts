import { expose } from 'comlink';

// Standard normal CDF approximation (Abramowitz & Stegun)
function normCdf(x: number): number {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;

  const sign = x < 0 ? -1 : 1;
  x = Math.abs(x);
  const t = 1.0 / (1.0 + p * x);
  const y = 1.0 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x / 2);
  return 0.5 * (1.0 + sign * y);
}

// Standard normal PDF
function normPdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

export interface GreeksInput {
  spot: number;
  strike: number;
  tte: number;      // Time to expiry in years
  vol: number;      // Implied volatility (annualized, e.g. 0.25 = 25%)
  rate: number;     // Risk-free rate (e.g. 0.05 = 5%)
  isCall: boolean;
}

export interface GreeksResult {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
  price: number;
}

function calculateGreeks(input: GreeksInput): GreeksResult {
  const { spot, strike, tte, vol, rate, isCall } = input;

  // Handle edge cases
  if (tte <= 0 || vol <= 0 || spot <= 0 || strike <= 0) {
    const intrinsic = isCall
      ? Math.max(spot - strike, 0)
      : Math.max(strike - spot, 0);
    return { delta: isCall ? (spot > strike ? 1 : 0) : (spot < strike ? -1 : 0), gamma: 0, theta: 0, vega: 0, rho: 0, price: intrinsic };
  }

  const sqrtT = Math.sqrt(tte);
  const d1 = (Math.log(spot / strike) + (rate + 0.5 * vol * vol) * tte) / (vol * sqrtT);
  const d2 = d1 - vol * sqrtT;

  const nd1 = normCdf(d1);
  const nd2 = normCdf(d2);
  const nNd1 = normCdf(-d1);
  const nNd2 = normCdf(-d2);
  const pd1 = normPdf(d1);

  const expRt = Math.exp(-rate * tte);

  let price: number;
  let delta: number;
  let rho: number;

  if (isCall) {
    price = spot * nd1 - strike * expRt * nd2;
    delta = nd1;
    rho = strike * tte * expRt * nd2 / 100;
  } else {
    price = strike * expRt * nNd2 - spot * nNd1;
    delta = nd1 - 1;
    rho = -strike * tte * expRt * nNd2 / 100;
  }

  const gamma = pd1 / (spot * vol * sqrtT);
  const theta = (-(spot * pd1 * vol) / (2 * sqrtT) - rate * strike * expRt * (isCall ? nd2 : -nNd2)) / 365;
  const vega = spot * pd1 * sqrtT / 100;

  return { delta, gamma, theta, vega, rho, price };
}

const greeksAPI = {
  calculate(input: GreeksInput): GreeksResult {
    return calculateGreeks(input);
  },

  batchCalculate(inputs: GreeksInput[]): GreeksResult[] {
    return inputs.map(calculateGreeks);
  },
};

expose(greeksAPI);
