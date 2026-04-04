# SPY Intraday Price Movement Factors: Comprehensive Reference (100+)

**Purpose:** This document catalogs measurable factors used in 0DTE options trading pattern recognition systems, with emphasis on order flow, volatility dynamics, and market microstructure.

**Date Created:** 2026-03-31
**Target Asset:** SPY (S&P 500 ETF Trust)
**Trading Horizon:** 0DTE intraday (tick to minutes)

---

## Table of Contents
1. [Order Flow & Volume Metrics](#1-order-flow--volume-metrics)
2. [Volatility Factors](#2-volatility-factors)
3. [Options Market & Greeks](#3-options-market--greeks)
4. [Price Structure & Technical](#4-price-structure--technical)
5. [Intermarket Correlation](#5-intermarket-correlation)
6. [Time & Calendar Factors](#6-time--calendar-factors)
7. [Market Microstructure](#7-market-microstructure)
8. [Sentiment & Positioning](#8-sentiment--positioning)
9. [Regime Detection](#9-regime-detection)
10. [Exotic/Specialized Metrics](#10-exotic-specialized-metrics)

---

## 1. Order Flow & Volume Metrics

### 1.1 Cumulative Volume Delta (CVD)
- **Category:** Order Flow
- **Description:** Running sum of buy volume minus sell volume. Positive CVD indicates buying pressure dominance; negative indicates selling pressure. Key signal for directional momentum.
- **Data Source:** ThetaData (tick-level tape data)
- **Timeframe Relevance:** Tick-level, 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** CVD = Σ(buy_volume - sell_volume) from session start or reference point

### 1.2 Volume-Weighted Average Price (VWAP)
- **Category:** Order Flow / Price Structure
- **Description:** Average price weighted by trading volume. Price above VWAP suggests buying pressure; below suggests selling pressure. Key level for execution algorithms.
- **Data Source:** ThetaData, Alpaca
- **Timeframe Relevance:** Tick-level, 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** VWAP = Σ(price × volume) / Σ(volume)

### 1.3 On-Balance Volume (OBV)
- **Category:** Order Flow
- **Description:** Cumulative indicator adding volume when close > previous close, subtracting when close < previous close. Detects volume divergences from price action.
- **Data Source:** Alpaca (OHLCV), ThetaData
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** OBV = prior_OBV ± volume based on close direction

### 1.4 Money Flow Index (MFI)
- **Category:** Order Flow
- **Description:** Momentum oscillator combining price and volume (14-period standard). Values >80 suggest overbought; <20 oversold. Detects exhaustion conditions in intraday moves.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** MFI = 100 - (100 / (1 + MFR)) where MFR = positive_money_flow / negative_money_flow

### 1.5 VPIN (Volume-Synchronized Probability of Informed Trading)
- **Category:** Order Flow
- **Description:** Proprietary metric (Easley, Lopez de Prado) measuring likelihood of informed trading. Values >0.5 indicate informed trading presence; spikes precede volatility expansion.
- **Data Source:** ThetaData (if available), calculated from tick data
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** Complex; requires tick-by-tick bid-ask data and volume bars
- **Reference:** See Easley et al., "The Volume Clock" (Algo Trading papers)

### 1.6 Aggressive Buy Volume Ratio
- **Category:** Order Flow
- **Description:** Percentage of volume executed at ask (aggressive buys) vs. total volume. >60% indicates sustained buying pressure; <40% indicates selling pressure.
- **Data Source:** ThetaData (requires tick tape classification)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** Aggressive_Buy_Ratio = Σ(ask_executed_volume) / Σ(all_volume)

### 1.7 Large Block Absorption
- **Category:** Order Flow
- **Description:** Detection of block trades (typically >10,000 shares) and whether market absorbs them (price continues in direction) or rejects them (reverses). Tracks institutional order impact.
- **Data Source:** ThetaData (block trade tracking)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** Track block trades >threshold; measure follow-through bars post-block

### 1.8 Dark Pool Volume Imbalance
- **Category:** Order Flow / Market Microstructure
- **Description:** Difference between dark pool buys and sells (from FINRA trades report or ATS data). Sustained imbalance suggests institutional accumulation/distribution.
- **Data Source:** FINRA OTC Trade Reporting, ThetaData (dark pool aggregation)
- **Timeframe Relevance:** Daily, 5min aggregate
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Dark_Pool_Buy_Sell_Imbalance = dark_buy_volume - dark_sell_volume

### 1.9 Sweep Orders (Aggressive Options-Linked Buying)
- **Category:** Order Flow
- **Description:** Large aggressive orders that "sweep" multiple offer levels at once, indicating urgent buying/selling from institutions or floor traders. Often precedes move in direction of sweep.
- **Data Source:** ThetaData (level 2/3 data, order book reconstruction)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** Track orders executing across multiple levels in single execution

### 1.10 Cumulative Delta - 5 Minute Bars
- **Category:** Order Flow
- **Description:** Buy volume minus sell volume per 5-minute candle. Positive delta bars indicate accumulation; negative indicate distribution. Sequence of bars shows momentum direction.
- **Data Source:** ThetaData, Alpaca (with classification)
- **Timeframe Relevance:** 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** Bar_Delta = bar_buy_volume - bar_sell_volume

### 1.11 Volume Profile / Point of Control (POC)
- **Category:** Order Flow / Price Structure
- **Description:** Most traded price level within defined period. Price pulled toward/away from POC indicates mean reversion vs. breakout behavior.
- **Data Source:** ThetaData (tick data), Alpaca
- **Timeframe Relevance:** 5min, 15min, hourly
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Histogram of volume by price level; POC = price with max cumulative volume

### 1.12 Imbalance Ratio (Buy Volume / Total Volume)
- **Category:** Order Flow
- **Description:** Simple metric: (total_buy_volume / total_volume) × 100. >60% sustained = buying dominance; <40% = selling dominance. Used for short-term directional bias.
- **Data Source:** ThetaData
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** Imbalance_Ratio = (buy_volume / (buy_volume + sell_volume)) × 100

### 1.13 Volume Rate of Change (ROC)
- **Category:** Order Flow
- **Description:** Percentage change in volume vs. N periods ago (e.g., 5-period). Spikes indicate volume expansion, often preceding volatility expansion.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Volume_ROC = ((current_volume - volume_N_periods_ago) / volume_N_periods_ago) × 100

### 1.14 Average True Range (ATR) - Volume Normalized
- **Category:** Order Flow / Volatility
- **Description:** ATR divided by average volume shows volatility per unit volume. Expanding volatility on declining volume = weak move; expanding volatility on rising volume = strong conviction.
- **Data Source:** Alpaca (OHLCV, calculate ATR)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Normalized_ATR = ATR(period) / SMA(volume, period)

### 1.15 Bid-Ask Volume Imbalance
- **Category:** Order Flow / Market Microstructure
- **Description:** Difference between cumulative bid-side volume initiated vs. ask-side volume initiated. Positive = buying; negative = selling. More granular than buy/sell classification.
- **Data Source:** ThetaData (level 2+ data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** BA_Imbalance = bid_initiated_volume - ask_initiated_volume

### 1.16 Momentum Divergence (CVD vs. Price)
- **Category:** Order Flow
- **Description:** When price makes new highs but CVD does not (or vice versa), divergence signals exhaustion or reversal. Bullish/bearish divergence detection.
- **Data Source:** ThetaData
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Compare peaks/troughs in CVD vs. price chart

### 1.17 Volume Basket Index (Relative Volume to 21-Day Average)
- **Category:** Order Flow
- **Description:** Current volume divided by 21-day average volume. >1.5x = abnormally high volume (often institutional activity); <0.75x = low volume (low conviction moves).
- **Data Source:** Alpaca
- **Timeframe Relevance:** Daily aggregate (intraday rolling window)
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Volume_Basket = current_volume / average_volume(21 days)

### 1.18 Seller Exhaustion - Reversal Volume
- **Category:** Order Flow
- **Description:** When selling volume peaks and then drops sharply, indicates seller exhaustion. Combined with positive CVD rebound = bullish setup.
- **Data Source:** ThetaData
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Manual pattern detection or spike identification in sell volume

### 1.19 Flow Toxicity Proxy (VPIN-Like Simplified Metric)
- **Category:** Order Flow
- **Description:** Percentage of volume reversing direction within N ticks (e.g., 10 ticks). High toxicity = adverse selection present; often spikes before institutional entries/exits.
- **Data Source:** ThetaData (tick data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** Track reversal patterns in tick sequence

### 1.20 Inter-Candle Volume Acceleration
- **Category:** Order Flow
- **Description:** Rate of volume acceleration across consecutive bars. Positive acceleration = momentum building; negative = momentum fading. Early momentum detection.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Accel = (volume[t] - volume[t-1]) - (volume[t-1] - volume[t-2])

---

## 2. Volatility Factors

### 2.1 VIX (Volatility Index)
- **Category:** Volatility
- **Description:** 30-day implied volatility of SPX index options. Rising VIX indicates fear and increasing expected volatility; falling indicates complacency. Inversely correlated with SPY on market stress.
- **Data Source:** ThetaData (VIX real-time), external feeds (CBOE)
- **Timeframe Relevance:** Daily, minute-level real-time
- **Priority for 0DTE:** HIGH
- **Calculation:** Index derived from SPX option prices; provided by CBOE

### 2.2 VVIX (Volatility of Volatility)
- **Category:** Volatility
- **Description:** Measures volatility of VIX itself (30-day implied vol of VIX options). Spikes indicate VIX is becoming unstable; high VVIX = uncertain regime.
- **Data Source:** ThetaData, external feeds (CBOE)
- **Timeframe Relevance:** Daily, minute-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Volatility of VIX options; index published by CBOE

### 2.3 Realized Volatility (Historical Volatility)
- **Category:** Volatility
- **Description:** Standard deviation of recent log returns (e.g., 20-period or 5-day rolling). Contrasts with implied volatility to detect vol crush or vol expansion potential.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min, daily
- **Priority for 0DTE:** HIGH
- **Calculation:** StDev(ln(close[t] / close[t-1]), period)

### 2.4 Implied Volatility Surface Slope
- **Category:** Volatility / Options Market
- **Description:** IV skew across strikes (e.g., IV(put strike) - IV(call strike)). Positive skew = put premium; often increases intraday on risk-off. Slope changes predict direction reversals.
- **Data Source:** ThetaData (SPX/SPY option IV surface)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** IV(OTM puts) - IV(ATM calls) across defined strike range

### 2.5 IV Term Structure (Front Month vs. Next Month)
- **Category:** Volatility / Options Market
- **Description:** Difference in IV between front-month and second-month options. Contango (front < next) = normal; backwardation (front > next) = stress/gamma. Changes drive gamma hedging flows.
- **Data Source:** ThetaData (option IV by expiration)
- **Timeframe Relevance:** Daily, intraday hourly
- **Priority for 0DTE:** HIGH
- **Calculation:** IV_front_month - IV_second_month

### 2.6 Volatility of Bid-Ask Spreads
- **Category:** Volatility / Market Microstructure
- **Description:** Intraday changes in bid-ask spread width. Widening spreads = declining liquidity / increasing uncertainty; narrowing = confidence. Spikes predict move momentum.
- **Data Source:** ThetaData (level 2 data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** StDev(spread) over sliding window

### 2.7 True Range Expansion
- **Category:** Volatility / Price Structure
- **Description:** Current true range (max(high, close[t-1]) - min(low, close[t-1])) compared to N-period average. >1.5x SMA(TR) = volatility expansion.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** HIGH
- **Calculation:** ATR_expansion = TR / SMA(TR, period)

### 2.8 Intraday VIX Acceleration
- **Category:** Volatility
- **Description:** Rate of change of VIX (e.g., VIX[t] - VIX[t-1min]). Positive acceleration = volatility expanding; useful for detecting vol regime shifts intraday.
- **Data Source:** ThetaData (minute VIX feed)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** dVIX = VIX[t] - VIX[t-1]

### 2.9 Realized Volatility vs. Implied Volatility Ratio
- **Category:** Volatility
- **Description:** (Realized Vol / Implied Vol) ratio. >1 = IV underestimated future volatility (often bullish skew); <1 = IV overestimated (often consolidation or fade opportunity).
- **Data Source:** ThetaData (IV), Alpaca (realized vol calculation)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** HIGH
- **Calculation:** RV / IV where RV = STDev(returns, period)

### 2.10 Volatility Clustering Index
- **Category:** Volatility
- **Description:** Detects if recent volatility is unusually elevated compared to historical baseline (e.g., current 5-min vol vs. 20-day average volatility). Identifies vol spike regimes.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Current_Vol / Historical_Vol_Average

### 2.11 Parkinson Volatility (High-Low Range)
- **Category:** Volatility
- **Description:** Alternative volatility estimator using high-low range (ignores open/close). More efficient than close-to-close. (High - Low) / Midpoint captures intrabar movement.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** σ_parkinson = ln(High / Low) / (2 × sqrt(ln(4)))

### 2.12 Garman-Klass Volatility
- **Category:** Volatility
- **Description:** Volatility estimator incorporating open, high, low, close. More robust than Parkinson. Useful for high-frequency data quality assessment.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Complex; accounts for overnight gaps and intrabar extremes

### 2.13 Rolling Beta (SPY vs. VIX)
- **Category:** Volatility
- **Description:** Correlation and beta of SPY returns vs. VIX changes. Negative beta typical (stocks down = VIX up); breakdown in relationship signals regime shift.
- **Data Source:** ThetaData (VIX), Alpaca (SPY)
- **Timeframe Relevance:** Daily, intraday rolling window
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Beta(SPY_returns, VIX_changes) using rolling 20-bar window

### 2.14 Volatility Half-Life (Mean Reversion Speed)
- **Category:** Volatility
- **Description:** Time required for volatility to revert halfway to its long-term mean. Short half-life = fast mean reversion; long = vol regime persistence. Dictates holding period.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** Daily, intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Exponential regression of vol decay; solve for half-life coefficient

### 2.15 Jump Risk Indicator (Overnight Gap Size)
- **Category:** Volatility
- **Description:** Size of opening gap relative to prior close and ATR. Large gaps = jump risk present; predicts higher intraday volatility and larger moves.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Daily open to market open
- **Priority for 0DTE:** MEDIUM
- **Calculation:** |open - prev_close| / ATR

---

## 3. Options Market & Greeks

### 3.1 Gamma Exposure Index (GEX)
- **Category:** Options Market / Intermarket
- **Description:** Dollar-weighted gamma from all SPX/SPY options. Positive GEX = market is gamma-stabilizing (dealers short vol); negative = gamma-destabilizing (dealers long vol). Predicts volatility trajectory and support/resistance levels.
- **Data Source:** ThetaData, specialty providers (Datadex, Citadel Analytics - if available)
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** GEX = Σ(gamma × spot_price² × open_interest × 100 × vega_dollar_per_point)

### 3.2 Delta Exposure Index (DEX)
- **Category:** Options Market
- **Description:** Sum of dealer delta exposure from all SPX/SPY options. Positive DEX = dealers long delta (market may face resistance on upside); negative = dealers short delta (market may face support on downside).
- **Data Source:** ThetaData, specialty providers
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** DEX = Σ(delta × open_interest × spot_price × multiplier) signed by dealer side

### 3.3 Put/Call Ratio - Volume
- **Category:** Options Market
- **Description:** Ratio of put volume to call volume intraday (e.g., rolling 5-min sum). >1.2 = fear/hedging; <0.8 = greed/calls. Sentiment indicator; extremes often precede reversals.
- **Data Source:** ThetaData (option trade flow)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** PC_ratio = put_volume / call_volume over period

### 3.4 Put/Call Ratio - Open Interest
- **Category:** Options Market
- **Description:** Ratio of put open interest to call open interest across all expirations. >1 = bearish skew; <1 = bullish skew. Structural positioning indicator.
- **Data Source:** ThetaData (option open interest)
- **Timeframe Relevance:** Daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** PC_OI_ratio = put_OI / call_OI

### 3.5 Max Pain Level
- **Category:** Options Market / Price Structure
- **Description:** Strike price where maximum option holder losses occur at expiration. Market often gravitates toward max pain in final day/hours. Locates equilibrium strike.
- **Data Source:** ThetaData (option open interest, calculated)
- **Timeframe Relevance:** Daily, updates intraday
- **Priority for 0DTE:** HIGH (especially critical for 0DTE)
- **Calculation:** Scan all strikes; calculate P&L for holders at each strike; find maximum loss

### 3.6 Vega-Weighted IV (Market IV)
- **Category:** Options Market
- **Description:** IV weighted by vega (sensitivity to IV changes) across options chain. More sensitive to market-moving strikes. Represents true market IV consensus.
- **Data Source:** ThetaData (option prices/greeks)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** Σ(IV × vega) / Σ(vega)

### 3.7 Option Gamma Concentration (Gamma at Strike)
- **Category:** Options Market / Price Structure
- **Description:** Gamma density at specific price levels. High gamma = sticky levels (acceleration if broken); low gamma = slippery levels. Guides breakout probability.
- **Data Source:** ThetaData (option greeks at strike)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** Gamma = (vega × change_in_IV) / (100 × stock_price × sigma × sqrt(days_to_expiry))

### 3.8 Charm (Gamma Decay Rate)
- **Category:** Options Market
- **Description:** Rate of change of delta over time. Positive charm = delta increases daily (favorable for long gamma); negative = delta decreases daily. Predicts overnight gap risk and daily decay patterns.
- **Data Source:** ThetaData (calculated from option prices)
- **Timeframe Relevance:** Daily, important at EOD
- **Priority for 0DTE:** HIGH (critical for 0DTE; charm accelerates near expiration)
- **Calculation:** Charm = -vega × (r + (dividend_yield) - (sigma² / 2)) - vega × (delta / (2 × time_to_expiry))

### 3.9 Vanna (Vega-Gamma Cross Exposure)
- **Category:** Options Market
- **Description:** Sensitivity of vega to spot price changes. Positive vanna = buying calls/selling puts improves with market up; structure-dependent gamma/vega interaction. Guides gamma flow direction.
- **Data Source:** ThetaData (calculated from option prices)
- **Timeframe Relevance:** 1min, 5min, daily
- **Priority for 0DTE:** HIGH
- **Calculation:** Vanna = -vega × (spot × sigma / spot) = -vega × sigma × (1 / spot)

### 3.10 Volga (Vega Convexity)
- **Category:** Options Market
- **Description:** Sensitivity of vega to IV changes. Positive volga = vega increases as IV rises (amplifies gains from vol expansion); negative = vega decreases (curbs gains). Predicts vol-on-vol dynamics.
- **Data Source:** ThetaData (calculated)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Volga = vega × (ln(F/K)² - sigma² × T) / sigma²

### 3.11 Dealer Delta Rehedging Pressure
- **Category:** Options Market / Order Flow
- **Description:** Change in dealer delta exposure requires mechanical rehedging (buy/sell underlying). Positive delta growth = sell pressure (dealers rehedge); negative = buy pressure. Drives liquidity supply/demand.
- **Data Source:** ThetaData (calculated from DEX changes)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** HIGH
- **Calculation:** dDEX = DEX[t] - DEX[t-1]; signed direction predicts rehedge flow

### 3.12 Dealer Gamma Positioning (Gamma Index)
- **Category:** Options Market
- **Description:** Aggregated gamma from dealer book (short gamma = dealers long vol, long gamma = dealers short vol). Predicts volatility trajectory and gamma hedging cascades.
- **Data Source:** ThetaData, specialty providers
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** Sum of all option gamma signed by dealer directional exposure

### 3.13 Charm Acceleration (2nd Derivative of Delta)
- **Category:** Options Market
- **Description:** Rate of change of charm. High charm acceleration = rapid delta decay approaching expiration (0DTE sensitive). Useful for pinpointing strike rotation thresholds.
- **Data Source:** ThetaData (calculated from successive charm values)
- **Timeframe Relevance:** Hourly, final hours of 0DTE
- **Priority for 0DTE:** HIGH
- **Calculation:** dCharm = Charm[t] - Charm[t-1]

### 3.14 Call Skew Intensity (Deep OTM Call IV)
- **Category:** Options Market
- **Description:** IV of far OTM calls relative to ATM calls. High skew = bullish tail risk premium. Tracks market's belief in upside moves and flow of tail hedgers.
- **Data Source:** ThetaData (option IV by strike)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IV(OTM calls far from strike) - IV(ATM calls)

### 3.15 Put Skew Intensity (Deep OTM Put IV)
- **Category:** Options Market
- **Description:** IV of far OTM puts relative to ATM puts. High put skew = bearish tail risk premium. Opposite of call skew; tracks hedging demand.
- **Data Source:** ThetaData (option IV by strike)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IV(OTM puts far from strike) - IV(ATM puts)

### 3.16 Implied Skewness (Options-Implied)
- **Category:** Options Market
- **Description:** Volatility smile curvature extrapolated into skewness. Right skew (bullish) = market prices higher probability of upside move; left skew (bearish) = downside focus.
- **Data Source:** ThetaData (option IV surface)
- **Timeframe Relevance:** Daily, intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Derived from IV smile shape; negative slope = right skew (bullish)

### 3.17 Implied Kurtosis (Tail Risk)
- **Category:** Options Market
- **Description:** Excess kurtosis from option prices. High kurtosis = market prices larger tail moves; low = normal tail assumptions. Predicts binary event risk.
- **Data Source:** ThetaData (option IV surface)
- **Timeframe Relevance:** Daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Derived from IV smile curvature relative to Black-Scholes

### 3.18 Dealer Vega Exposure (Vega Weighted)
- **Category:** Options Market
- **Description:** Dollar vega exposure from dealer book. Positive = dealers long vol exposure; likely to suppress IV spikes. Negative = dealers short vol; likely amplifies vol expansion.
- **Data Source:** ThetaData, specialty providers
- **Timeframe Relevance:** Daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Σ(vega × contract_multiplier × open_interest)

### 3.19 Option Open Interest Ladder (Support/Resistance by Strike)
- **Category:** Options Market / Price Structure
- **Description:** Aggregated call + put OI at each strike. Levels with high OI act as "sticky" levels where gamma hedging is concentrated. Maps support/resistance grid.
- **Data Source:** ThetaData (option open interest)
- **Timeframe Relevance:** Daily, updates intraday
- **Priority for 0DTE:** HIGH
- **Calculation:** OI_ladder[strike] = call_OI[strike] + put_OI[strike]

### 3.20 Put/Call OI Imbalance by Strike
- **Category:** Options Market
- **Description:** For each strike, (put_OI - call_OI). Positive = put concentration (bearish sentiment); negative = call concentration (bullish sentiment). Maps directional gamma positioning.
- **Data Source:** ThetaData
- **Timeframe Relevance:** Daily, updates intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** PC_OI_imbalance[strike] = put_OI[strike] - call_OI[strike]

### 3.21 Zero-DTE Specific: Final Hour Charm Spike
- **Category:** Options Market / Time-Based
- **Description:** Final hour before 0DTE expiration, charm accelerates dramatically as delta rotation intensifies. Critical for final-hour move prediction.
- **Data Source:** ThetaData (0DTE option greeks)
- **Timeframe Relevance:** Minute-level in final hour
- **Priority for 0DTE:** HIGH
- **Calculation:** Charm[t] in final 60 minutes; track spike acceleration

---

## 4. Price Structure & Technical

### 4.1 High of Day (HOD) Distance
- **Category:** Price Structure
- **Description:** Distance from current price to intraday high. Measures how extended move is toward resistance. Helps identify overbought conditions and reversal risk.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Intraday real-time
- **Priority for 0DTE:** HIGH
- **Calculation:** HOD - current_price; typically measured in percentage or dollar terms

### 4.2 Low of Day (LOD) Distance
- **Category:** Price Structure
- **Description:** Distance from current price to intraday low. Measures rebound potential. Helps identify oversold conditions and support proximity.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Intraday real-time
- **Priority for 0DTE:** HIGH
- **Calculation:** current_price - LOD

### 4.3 Range Extension (Current Range vs. Historical 20-Day Range)
- **Category:** Price Structure
- **Description:** Intraday range to date vs. typical 20-day intraday range. >1.3x = unusually large range (high conviction or news-driven); <0.7x = contained (consolidation expected).
- **Data Source:** Alpaca
- **Timeframe Relevance:** Intraday updates
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Current_Range / Avg_20Day_Range where Range = HOD - LOD

### 4.4 Previous Close Distance
- **Category:** Price Structure
- **Description:** Distance from current price to previous day's close. Positive = gap up recovery; negative = gap down recovery. Tracks overnight gap closure.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** current_price - prev_close_price

### 4.5 VWAP Deviation
- **Category:** Price Structure / Order Flow
- **Description:** (Current Price - VWAP) / VWAP × 100. Positive = above fair value (buying pressure extended); negative = below fair value (selling pressure extended). Reversion target.
- **Data Source:** ThetaData, Alpaca
- **Timeframe Relevance:** Tick-level, 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** (price - VWAP) / VWAP × 100

### 4.6 Simple Moving Average (SMA) 20-Period
- **Category:** Price Structure
- **Description:** 20-period simple moving average (5-minute bars = ~100 min). Price above SMA = short-term uptrend; below = downtrend. Primary trend filter.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** SMA(close, 20)

### 4.7 Exponential Moving Average (EMA) 12-Period
- **Category:** Price Structure
- **Description:** 12-period EMA (more responsive to recent price). EMA > SMA = momentum; EMA < SMA = fading momentum. Faster trend detector.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** EMA(close, 12) with alpha = 2/(12+1)

### 4.8 RSI (Relative Strength Index) 14-Period
- **Category:** Price Structure
- **Description:** Oscillator measuring overbought (>70) / oversold (<30) conditions. >70 = potential reversal down; <30 = potential reversal up. Intraday mean reversion indicator.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** RSI = 100 - (100 / (1 + RS)) where RS = avg_gain / avg_loss

### 4.9 Bollinger Bands Width (Upper - Lower)
- **Category:** Price Structure
- **Description:** Distance between upper and lower Bollinger Bands (20-period, 2 std dev). Expanding bands = volatility expansion; contracting = volatility compression. Squeeze setups.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Upper_Band - Lower_Band where bands = SMA ± (2 × StDev)

### 4.10 Bollinger Bands %B (Position Within Bands)
- **Category:** Price Structure
- **Description:** (Price - Lower_Band) / (Upper_Band - Lower_Band) × 100. 0 = at lower band; 100 = at upper band; 50 = mid-band. Locates position in volatility range.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** %B = (close - lower_band) / (upper_band - lower_band) × 100

### 4.11 Keltner Channel Position
- **Category:** Price Structure
- **Description:** ATR-based channels (similar to Bollinger but using ATR instead of StDev). Position in Keltner channel shows volatility-adjusted support/resistance.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Keltner = SMA ± (ATR × 2); %K = (close - lower) / (upper - lower)

### 4.12 Pivot Points (Daily)
- **Category:** Price Structure
- **Description:** Daily pivot levels: PP (pivot point), R1/R2 (resistance), S1/S2 (support). Historically significant levels; market often gravitates toward pivot. Key levels for 0DTE.
- **Data Source:** Alpaca (prior day OHLC)
- **Timeframe Relevance:** Daily (applied intraday)
- **Priority for 0DTE:** HIGH
- **Calculation:** PP = (H + L + C) / 3; R1 = (2×PP) - L; S1 = (2×PP) - H; R2 = PP + (H-L); S2 = PP - (H-L)

### 4.13 Fibonacci Retracements
- **Category:** Price Structure
- **Description:** Key levels at 23.6%, 38.2%, 50%, 61.8%, 78.6% of recent swing. Market often respects Fibonacci levels; useful for predicting pullback targets.
- **Data Source:** Alpaca (calculated from swing high/low)
- **Timeframe Relevance:** Intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** From recent swing; levels = swing_start + (swing_size × fib_ratio)

### 4.14 Market Profile - Point of Control (POC)
- **Category:** Price Structure
- **Description:** Most traded price level in recent period. Market gravitates toward POC. Deviation from POC predicts mean reversion direction.
- **Data Source:** ThetaData (tick data), calculated from volume profile
- **Timeframe Relevance:** 5min, hourly
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Histogram of volume by price; POC = max cumulative volume price

### 4.15 Volume-Based Support/Resistance
- **Category:** Price Structure / Order Flow
- **Description:** Price levels showing high volume concentration. These act as sticky levels where gamma accumulates. Identifies true supply/demand zones.
- **Data Source:** ThetaData (volume profile)
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** Identify price levels with top 10-20% cumulative volume

### 4.16 Trend Direction (Price vs. 50-SMA)
- **Category:** Price Structure
- **Description:** Binary indicator: price above 50-SMA = uptrend; below = downtrend. Simple directional bias filter.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** HIGH
- **Calculation:** 50-SMA; compare to current price

### 4.17 Linear Regression Slope (20-Period)
- **Category:** Price Structure
- **Description:** Slope of linear regression line over past 20 bars. Positive slope = uptrend momentum; negative = downtrend momentum. Magnitude shows momentum strength.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Linear regression of close prices; slope coefficient

### 4.18 Price Pattern: Double Bottom / Double Top
- **Category:** Price Structure
- **Description:** Reversal pattern where price tests level twice and bounces (double bottom = bullish) or peaks twice and reverses (double top = bearish). Predicts momentum shift.
- **Data Source:** Alpaca (calculated from swing analysis)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Pattern recognition; compare swing lows/highs

### 4.19 Head and Shoulders Pattern
- **Category:** Price Structure
- **Description:** Classic reversal pattern (left shoulder, head, right shoulder). Completion signals strong directional reversal. Often precedes significant intraday reversal.
- **Data Source:** Alpaca (calculated from swing analysis)
- **Timeframe Relevance:** 15min, hourly
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Pattern recognition; volume validation important

### 4.20 Gap Fill Probability
- **Category:** Price Structure
- **Description:** Percentage likelihood of intraday gap closure based on historical data. Large unfilled gaps early in session predict mean reversion.
- **Data Source:** Alpaca (historical analysis)
- **Timeframe Relevance:** Daily (applied intraday)
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Historical gap closure rate by gap size

---

## 5. Intermarket Correlation

### 5.1 QQQ (Nasdaq-100) Relative Strength
- **Category:** Intermarket Correlation
- **Description:** QQQ vs. SPY momentum/correlation. QQQ stronger = tech-driven market (mega-cap sensitive); QQQ weaker = SPY outperforming (value/dividend driven). Drives sector rotation.
- **Data Source:** Alpaca (QQQ, SPY real-time)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** HIGH
- **Calculation:** (QQQ_return - SPY_return) or correlation(QQQ, SPY) in rolling window

### 5.2 DIA (Dow Jones Industrial Average)
- **Category:** Intermarket Correlation
- **Description:** DIA (blue chips, 30 stocks) vs. SPY momentum. DIA stronger = large-cap defensive; DIA weaker = leadership in mid/small-cap. Identifies broad vs. narrow market.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (DIA_return - SPY_return) or correlation(DIA, SPY)

### 5.3 IWM (Russell 2000 Small-Cap)
- **Category:** Intermarket Correlation
- **Description:** IWM (small-cap) vs. SPY momentum. IWM stronger = risk-on sentiment; IWM weaker = flight-to-quality. Risk sentiment barometer.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (IWM_return - SPY_return) or correlation(IWM, SPY)

### 5.4 S&P 500 Breadth (Advance/Decline Line)
- **Category:** Intermarket Correlation
- **Description:** Number of advancing stocks minus declining stocks in S&P 500. Breadth divergence (price high but breadth weak) signals market top; breadth strength signals sustained rally.
- **Data Source:** NYSE TICK data, external feeds (CBOE, FinViz)
- **Timeframe Relevance:** Daily (minute-level updates available)
- **Priority for 0DTE:** HIGH
- **Calculation:** Cumulative(advance_count - decline_count)

### 5.5 Market Breadth Ratio (Advance/Total)
- **Category:** Intermarket Correlation
- **Description:** (Advancing stocks) / (Total advancing + declining stocks). >60% = strong uptrend; <40% = strong downtrend. Real-time market health check.
- **Data Source:** NYSE TICK, external data
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** advancing / (advancing + declining)

### 5.6 NYSE Tick Index (TICK)
- **Category:** Market Microstructure / Intermarket
- **Description:** Number of stocks with uptick minus downtick on NYSE. Positive TICK = buying pressure; negative = selling pressure. Real-time market sentiment; extreme levels (>1000 or <-1000) signal exhaustion.
- **Data Source:** External feeds (ThinkOrSwim, TradingView, CBOE)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** upticks - downticks across NYSE stocks

### 5.7 TRIN (Arms Index)
- **Category:** Market Microstructure / Intermarket
- **Description:** (Advancing / Declining) / (Volume Up / Volume Down). <1 = breadth improving (bullish); >1 = breadth deteriorating (bearish). Breadth-adjusted volume indicator.
- **Data Source:** External feeds
- **Timeframe Relevance:** Daily, intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (AD ratio) / (vol_up / vol_down)

### 5.8 10-Year US Treasury Yield (TNX)
- **Category:** Intermarket Correlation
- **Description:** Inverse correlation with equities; rising yields = headwind for equities (higher discount rate). 10Y yield acceleration intraday predicts equity pressure; flattening predicts relief.
- **Data Source:** External feeds (CBOE, Bloomberg)
- **Timeframe Relevance:** Daily, hourly (intraday updates less reliable)
- **Priority for 0DTE:** MEDIUM
- **Calculation:** TNX real-time quotation

### 5.9 US Dollar Index (DXY)
- **Category:** Intermarket Correlation
- **Description:** Broad USD strength. Strong DXY = headwind for multinational equities (earnings drag); weak DXY = lift for EM exposures. Sector-specific impact.
- **Data Source:** External feeds (ICE, Refinitiv)
- **Timeframe Relevance:** Daily, hourly
- **Priority for 0DTE:** MEDIUM
- **Calculation:** DXY real-time quotation

### 5.10 Gold Futures (GC) vs. SPY
- **Category:** Intermarket Correlation
- **Description:** Inverse correlation; gold strength = risk-off sentiment; gold weakness = risk-on. Safe-haven indicator; sudden gold strength predicts equity weakness.
- **Data Source:** External feeds (CME futures)
- **Timeframe Relevance:** Daily, hourly
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (GC_return - SPY_return) or correlation(GC, SPY)

### 5.11 Crude Oil Futures (CL) vs. SPY
- **Category:** Intermarket Correlation
- **Description:** Cyclical indicator; oil strength = economic growth expectations; oil weakness = contraction fears. Energy sector driver.
- **Data Source:** External feeds (CME futures)
- **Timeframe Relevance:** Daily, hourly
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (CL_return - SPY_return) or correlation(CL, SPY)

### 5.12 Sector ETF Leadership
- **Category:** Intermarket Correlation
- **Description:** Track momentum of major sector ETFs (XLK, XLF, XLE, XLV, XLI, XLY, XLRE, XLU) vs. SPY. Leading sectors identify market leadership change.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Sector_return vs. SPY_return; track relative strength

### 5.13 Correlation Matrix (SPY vs. Major Indices)
- **Category:** Intermarket Correlation
- **Description:** Rolling correlation of SPY with QQQ, DIA, IWM, TLT (bonds). Breakdown in normal correlations signals regime shift or hedging activity.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Daily, intraday rolling window
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Correlation(SPY, [QQQ, DIA, IWM, TLT]) over 20-bar window

### 5.14 Credit Spreads (HY OAS - Investment Grade OAS)
- **Category:** Intermarket Correlation
- **Description:** High-yield vs. investment-grade spread. Widening = risk-off (equity pressure); tightening = risk-on (equity lift). Credit market leading equities during stress.
- **Data Source:** External feeds (Bloomberg, CME)
- **Timeframe Relevance:** Daily, hourly
- **Priority for 0DTE:** LOW (updated less frequently)
- **Calculation:** HY OAS - IG OAS

### 5.15 Equity Futures (ES) Leading SPY
- **Category:** Intermarket Correlation
- **Description:** E-mini S&P 500 futures (ES) leads cash SPY by minutes to hours. ES price action predicts SPY direction. Crucial for intraday setup timing.
- **Data Source:** External feeds (CME), some brokers provide real-time ES
- **Timeframe Relevance:** Tick-level, 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** ES_price direction vs. SPY_price; lag correlation

---

## 6. Time & Calendar Factors

### 6.1 Time Since Market Open (Minutes)
- **Category:** Time / Calendar
- **Description:** Minutes elapsed since 9:30 AM ET open. Market structure changes throughout session (first 30 min = high volatility; 11:30-1:00 = dull; 3:00-4:00 = power hour). Structural pattern.
- **Data Source:** Real-time clock
- **Timeframe Relevance:** Intraday real-time
- **Priority for 0DTE:** HIGH
- **Calculation:** Current time - market open (9:30 AM ET)

### 6.2 Time Until Market Close (Minutes)
- **Category:** Time / Calendar
- **Description:** Minutes remaining until 4:00 PM ET close. Increased gamma acceleration and volatility in final hour. Final 60 minutes dramatically different from mid-session.
- **Data Source:** Real-time clock
- **Timeframe Relevance:** Intraday real-time
- **Priority for 0DTE:** HIGH
- **Calculation:** Market close (4:00 PM ET) - current time

### 6.3 Opening Period (First 30 Minutes)
- **Category:** Time / Calendar
- **Description:** Binary flag for first 30 minutes of session (9:30-10:00 AM). High volatility, news absorption, inventory rebalancing. Different dynamics than rest of day.
- **Data Source:** Real-time clock
- **Timeframe Relevance:** First 30 min only
- **Priority for 0DTE:** HIGH
- **Calculation:** IF time_since_open < 30 THEN True

### 6.4 Power Hour (Last Hour)
- **Category:** Time / Calendar
- **Description:** Binary flag for 3:00-4:00 PM ET. Increased volatility, manager window trades, position squaring. Strong directional bias in power hour.
- **Data Source:** Real-time clock
- **Timeframe Relevance:** 3:00-4:00 PM ET only
- **Priority for 0DTE:** HIGH
- **Calculation:** IF time_until_close < 60 THEN True

### 6.5 Lunch Hour (11:30 AM - 1:00 PM)
- **Category:** Time / Calendar
- **Description:** Mid-day quiet period; lower volume, tighter spreads, reduced volatility. Consolidation patterns common. Risk-reward unfavorable during lunch.
- **Data Source:** Real-time clock
- **Timeframe Relevance:** 11:30 AM - 1:00 PM ET
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IF 11:30 <= time_of_day <= 13:00 THEN True

### 6.6 Day of Week
- **Category:** Time / Calendar
- **Description:** Categorical: Monday (post-weekend gap), Tuesday-Thursday (normal), Friday (position squaring). Each day has different characteristics.
- **Data Source:** Real-time calendar
- **Timeframe Relevance:** Daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Weekday enumeration (0=Monday, 4=Friday)

### 6.7 Monday Gap Behavior
- **Category:** Time / Calendar
- **Description:** Monday opens often have larger gaps post-weekend. Gap direction (up/down) and size predicts mean reversion vs. continuation dynamics.
- **Data Source:** Alpaca (prior Friday close vs. Monday open)
- **Timeframe Relevance:** Monday mornings
- **Priority for 0DTE:** MEDIUM
- **Calculation:** |Monday_open - Friday_close| / ATR

### 6.8 Friday Expiration Week (3DTE to 1DTE)
- **Category:** Time / Calendar
- **Description:** Options expiration week (Friday). Gamma effects intensify Wednesday-Friday. Max pain becomes critical. Volatility regime shifts.
- **Data Source:** Calendar
- **Timeframe Relevance:** Wednesday-Friday of expiration weeks
- **Priority for 0DTE:** HIGH
- **Calculation:** Days until next Friday expiration

### 6.9 FOMC Announcement Days
- **Category:** Time / Calendar / Macro Events
- **Description:** Federal Reserve interest rate decision days (8 per year, mid-month typically 2:00 PM ET). Massive volatility expansion expected; VIX spikes, implied volatility jumps. Trading dynamics fundamentally different.
- **Data Source:** Calendar (FOMC meeting schedule)
- **Timeframe Relevance:** Intraday (especially 1:30-2:30 PM ET)
- **Priority for 0DTE:** HIGH
- **Calculation:** IF date matches FOMC calendar THEN True

### 6.10 Economic Data Release Calendar
- **Category:** Time / Calendar / Macro Events
- **Description:** Non-farm payroll (1st Friday), CPI (monthly), jobless claims (weekly Thursday), retail sales (monthly). Scheduled news events spike volatility. Pre-event consolidation, post-event reversal common.
- **Data Source:** Economic calendar (TradingEconomics, Investing.com)
- **Timeframe Relevance:** Specific time windows (typically 8:30 AM or 10:00 AM ET)
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IF current_time within scheduled_release_window THEN True

### 6.11 Earnings Season Windows
- **Category:** Time / Calendar / Macro Events
- **Description:** Quarterly earnings periods (Jan-Feb, Apr-May, Jul-Aug, Oct-Nov). Increased SPX volatility; leadership rotations; daily VIX elevation. Market-wide IV shift.
- **Data Source:** Earnings calendar
- **Timeframe Relevance:** Multi-week periods 4x/year
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IF date in earnings_window THEN True

### 6.12 VIX Index Expiration Week (Monthly)
- **Category:** Time / Calendar
- **Description:** VIX options/futures expiration (typically 3rd Wednesday). Gamma effects in VIX drive SPX volatility. Pin to strike behavior; unusual daily moves.
- **Data Source:** Calendar (3rd Wednesday each month)
- **Timeframe Relevance:** Monthly (3rd Wednesday)
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Days until VIX expiration

### 6.13 End-of-Month / End-of-Quarter Effects
- **Category:** Time / Calendar
- **Description:** Position rebalancing, index reconstitution (end-quarter), fund window trades. Increased volume; mechanical flows. Predictable mean reversion if extreme.
- **Data Source:** Calendar
- **Timeframe Relevance:** Final 2-3 days of month/quarter
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IF date near end_of_month OR end_of_quarter THEN True

### 6.14 Holiday / Half-Day Market Effects
- **Category:** Time / Calendar
- **Description:** Days before holidays (reduced hours: close at 1:00 PM ET) or day after holidays (unusual open patterns). Lower participation; unusual moves. SPX closed holidays: MLK, Presidents, Memorial, Independence, Labor, Thanksgiving, Christmas.
- **Data Source:** Market holiday calendar
- **Timeframe Relevance:** Specific holiday calendars
- **Priority for 0DTE:** MEDIUM
- **Calculation:** IF date is holiday_eve OR holiday_after THEN True

### 6.15 Time Decay Acceleration (Theta Decay)
- **Category:** Time / Calendar / Options Market
- **Description:** For 0DTE options, theta decay accelerates exponentially in final hours. Average theta decay per hour increases 5-10x in final 2 hours. Critical for gamma/theta tradeoff.
- **Data Source:** Calculated from option prices
- **Timeframe Relevance:** Minute-level in final hours
- **Priority for 0DTE:** HIGH
- **Calculation:** Theta[final_2_hours] / Theta[morning]

### 6.16 Weekend Risk Premium (Friday Close)
- **Category:** Time / Calendar
- **Description:** Friday close exhibits premium for 3-day weekend risk (gap risk, geopolitical events). Friday close higher than Thursday close trend; weekend exposure cost.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Friday afternoon
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Track Friday premium vs. historical average

### 6.17 Overnight Index Futures (ES After-Hours)
- **Category:** Time / Calendar / Intermarket
- **Description:** E-mini S&P 500 futures trading 4:00 PM - 9:30 AM overnight. Overnight price action predicts next-day opening. Overnight high/low establish gaps.
- **Data Source:** CME futures
- **Timeframe Relevance:** After-hours (4:00 PM - 9:30 AM)
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Overnight_high - overnight_low; direction

---

## 7. Market Microstructure

### 7.1 Bid-Ask Spread (Percentage)
- **Category:** Market Microstructure
- **Description:** (Ask - Bid) / Midpoint × 100. Narrower spreads = better liquidity (0.1-0.3% typical). Widening spreads signal reduced liquidity or uncertainty.
- **Data Source:** ThetaData (level 2), Alpaca (real-time quote)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** (ask - bid) / ((ask + bid) / 2) × 100

### 7.2 Effective Spread (Trade-to-Midpoint)
- **Category:** Market Microstructure
- **Description:** Actual execution price vs. midpoint at time of trade. Measures realized slippage; effective spread vs. quoted spread (impact of execution). Key for trade execution quality.
- **Data Source:** ThetaData (tick-level trades)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** 2 × |trade_price - midpoint| / midpoint

### 7.3 Bid Depth (Volume at Best Bid)
- **Category:** Market Microstructure
- **Description:** Cumulative volume available at bid side (e.g., top 5 levels). Large bid depth = strong support; thin = weak support. Predicts support level strength.
- **Data Source:** ThetaData (level 2/3 data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** SUM(bid_volume, levels 1-5)

### 7.4 Ask Depth (Volume at Best Ask)
- **Category:** Market Microstructure
- **Description:** Cumulative volume available at ask side (e.g., top 5 levels). Large ask depth = strong resistance; thin = weak resistance. Predicts resistance level strength.
- **Data Source:** ThetaData (level 2/3 data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** SUM(ask_volume, levels 1-5)

### 7.5 Order Book Imbalance (Bid Depth - Ask Depth)
- **Category:** Market Microstructure / Order Flow
- **Description:** Cumulative bid depth minus ask depth. Positive = more bids than asks (bullish); negative = more asks than bids (bearish). Real-time directional pressure.
- **Data Source:** ThetaData (level 2)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** bid_depth - ask_depth

### 7.6 Order Flow Intensity (Order Imbalance per Dollar of Notional)
- **Category:** Market Microstructure / Order Flow
- **Description:** Signed order imbalance normalized by notional volume. High intensity = concentrated directional flow per unit volume; weak = dispersed flow.
- **Data Source:** ThetaData (level 2, require reconstructed order book)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** HIGH
- **Calculation:** Order_imbalance / notional_volume

### 7.7 Market Maker Inventory Risk (Spread Widening Pattern)
- **Category:** Market Microstructure
- **Description:** When spreads widen sharply, often signals market maker inventory imbalance. Widening during buying = MM short (needs to sell); widening during selling = MM long (needs to buy).
- **Data Source:** ThetaData (spread + volume data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Correlation of spread widening with directional volume

### 7.8 Large Order Placement (Hidden Orders Detection)
- **Category:** Market Microstructure / Order Flow
- **Description:** Detection of large orders placed and immediately canceled or partially filled (icebergs, spoofing-adjacent). Indicates institutional presence; liquidity taker ahead.
- **Data Source:** ThetaData (order book reconstruction)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Pattern recognition in order book visibility

### 7.9 Volatility of Spreads (Std Dev of Bid-Ask Width)
- **Category:** Market Microstructure
- **Description:** Standard deviation of spread sizes over recent period (e.g., 100 ticks). Increasing volatility of spreads = increasing uncertainty; spikes precede moves.
- **Data Source:** ThetaData
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** StDev(bid-ask spread, window=100 ticks)

### 7.10 Participation Rate (Volume / Average Volume per Period)
- **Category:** Market Microstructure / Order Flow
- **Description:** Current volume rate vs. typical rate. High participation = active trading (high conviction); low = passive (consolidation). Predicts move sustainability.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** current_volume_per_minute / historical_avg_volume_per_minute

### 7.11 VPIN (Volume-Synchronized Probability of Informed Trading) - Alternative Calculation
- **Category:** Market Microstructure / Order Flow
- **Description:** (See Order Flow section 1.5 for main entry). Alternative: count buy/sell volume bars; calculate symmetric distribution; deviation from center = informed trading probability.
- **Data Source:** ThetaData (tick-by-tick)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** HIGH
- **Calculation:** Advanced; requires academic reference (Easley, López de Prado)

### 7.12 Time-Weighted Average Price (TWAP)
- **Category:** Market Microstructure
- **Description:** Average price over time period (equal weight to each minute). Contrasts with VWAP; TWAP useful for algorithm execution quality assessment.
- **Data Source:** Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** LOW
- **Calculation:** SUM(price[t]) / number_of_periods

### 7.13 Executed Volume Concentration (Top-N Orders)
- **Category:** Market Microstructure / Order Flow
- **Description:** Percentage of total volume in top 5 (or 10) orders. High concentration = few large orders (institutional); low concentration = many small orders (retail).
- **Data Source:** ThetaData (tick-level trades)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (sum_of_top_5_orders / total_volume) × 100

### 7.14 Median Trade Size vs. Average Trade Size
- **Category:** Market Microstructure / Order Flow
- **Description:** If average >> median, indicates few large orders skewing distribution (institutional); if median ≈ average, more uniform retail participation.
- **Data Source:** ThetaData (tick-level trades)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Median(trade_size) vs. Mean(trade_size)

### 7.15 Market Depth Imbalance (Cumulative Weight)
- **Category:** Market Microstructure / Order Flow
- **Description:** Weighted order book depth incorporating distance from midpoint. Closer orders (at best bid/ask) weighted higher. Assesses true liquidity vs. posted liquidity.
- **Data Source:** ThetaData (level 2/3)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Σ(depth[level] / distance[level]) for bid and ask sides

---

## 8. Sentiment & Positioning

### 8.1 Put/Call Ratio (Options Volume - Real-Time)
- **Category:** Sentiment / Positioning
- **Description:** (See Options section 3.3). Rolling 5-minute put volume / call volume. Extreme readings (>2.0 or <0.5) often signal exhaustion.
- **Data Source:** ThetaData (option trade flow)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** put_volume / call_volume over rolling 5-min window

### 8.2 Put/Call Ratio - Premium (Dollar Value)
- **Category:** Sentiment / Positioning
- **Description:** Total put premium spent vs. call premium spent. >1 = fear (put buyers paying up); <1 = greed (call buyers dominant). More granular than volume alone.
- **Data Source:** ThetaData (option trade flow + prices)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** SUM(put_volume × put_price) / SUM(call_volume × call_price)

### 8.3 Call Spreads vs. Put Spreads Activity
- **Category:** Sentiment / Positioning
- **Description:** Ratio of call spread volume to put spread volume. High call spreads = bullish debit spreads; high put spreads = bearish positioning.
- **Data Source:** ThetaData (option trade flow)
- **Timeframe Relevance:** Daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** call_spread_volume / put_spread_volume

### 8.4 Flow Skewness (Buy vs. Sell Initiation)
- **Category:** Sentiment / Positioning
- **Description:** Percentage of options trades initiated as buys vs. sells. >60% buy = aggressive bullish; <40% = aggressive bearish. Detects money flow direction.
- **Data Source:** ThetaData (option trade classification)
- **Timeframe Relevance:** 5min, daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** buy_initiated_trades / total_trades

### 8.5 AAII Sentiment Index (American Association of Individual Investors)
- **Category:** Sentiment / Positioning
- **Description:** Weekly survey of retail investor sentiment. Bullish%, neutral%, bearish%. Extreme readings (>75% bullish or <20% bullish) often precede reversals. Contrarian indicator.
- **Data Source:** AAII (aaii.com), updated weekly
- **Timeframe Relevance:** Daily (updated weekly)
- **Priority for 0DTE:** LOW (updated weekly, less relevant intraday)
- **Calculation:** Published sentiment percentages

### 8.6 Investor Intelligence Sentiment
- **Category:** Sentiment / Positioning
- **Description:** Industry survey of investment advisory sentiment (bullish%, bearish%, neutral%). Extreme bull readings precede selloffs; extreme bear readings precede rallies.
- **Data Source:** Investor Intelligence (investorsintelligence.com)
- **Timeframe Relevance:** Daily (updated weekly)
- **Priority for 0DTE:** LOW
- **Calculation:** Published sentiment percentages

### 8.7 Fear & Greed Index
- **Category:** Sentiment / Positioning
- **Description:** Composite sentiment indicator combining VIX, market momentum, junk bond demand, market breadth, etc. High (>70) = greed (overbought); low (<30) = fear (oversold). Real-time gauge.
- **Data Source:** CNN Fear & Greed Index, other sentiment aggregators
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Composite of multiple sentiment metrics

### 8.8 Commitment of Traders (COT) Report
- **Category:** Sentiment / Positioning
- **Description:** CFTC positioning data for ES futures (commercial, non-commercial, retail). Extreme positioning (commercial long or short extreme) indicates crowded trades. Updated weekly Friday.
- **Data Source:** CFTC (cftc.gov), COT reports
- **Timeframe Relevance:** Weekly (updated Friday)
- **Priority for 0DTE:** LOW (weekly update too slow)
- **Calculation:** Published COT data

### 8.9 Fund Flow Indicators (Smart Money Tracking)
- **Category:** Sentiment / Positioning
- **Description:** Institutional fund inflows/outflows (tracked through options flow, dark pool activity, block trades). Positive flows = accumulation; negative = distribution.
- **Data Source:** ThetaData (order flow analysis), specialty providers
- **Timeframe Relevance:** Daily, intraday
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Aggregate of identified institutional block and dark pool flows

### 8.10 Short Interest Ratio (Shares Short / Float)
- **Category:** Sentiment / Positioning
- **Description:** Percentage of SPY shares short. Rising short interest = bearish sentiment; falling = bullish. Updates bi-weekly. Useful for positioning extremes.
- **Data Source:** Stock loan data providers (Markit, Regsho), updated bi-weekly
- **Timeframe Relevance:** Bi-weekly
- **Priority for 0DTE:** LOW (updates bi-weekly)
- **Calculation:** shares_short / float

### 8.11 Market-Neutral Strategy Inflows
- **Category:** Sentiment / Positioning
- **Description:** Hedge fund inflows into market-neutral strategies (often indicate hedging activity increase). Elevated flows precede volatility expansion.
- **Data Source:** NAAIM (National Association of Active Investment Managers) exposure index
- **Timeframe Relevance:** Weekly
- **Priority for 0DTE:** LOW
- **Calculation:** Published by NAAIM

### 8.12 Leveraged ETF Flow
- **Category:** Sentiment / Positioning
- **Description:** Inflows into 3x leveraged bull/bear ETFs. High leveraged long inflows = retail bullishness (often contrarian); high leveraged short = retail bearishness. Retail positioning gauge.
- **Data Source:** ETF flow tracking (ETF.com, Morningstar)
- **Timeframe Relevance:** Daily
- **Priority for 0DTE:** MEDIUM
- **Calculation:** inflow_tracking by fund

### 8.13 Insider Buying/Selling Activity
- **Category:** Sentiment / Positioning
- **Description:** Insider transactions (company executives buying/selling shares). Elevated insider buying = positive view (contrarian indicator for insider timing); selling = distribution (often correct timing).
- **Data Source:** SEC EDGAR, insider tracking sites
- **Timeframe Relevance:** Reported daily/weekly
- **Priority for 0DTE:** LOW (updated too slowly for intraday)
- **Calculation:** Count of insider buy vs. sell transactions

### 8.14 Conference Call Sentiment (Earnings Season)
- **Category:** Sentiment / Positioning
- **Description:** Management tone in earnings calls (track via sentiment analysis tools). Bullish tone = future strength; bearish tone = weakness. Useful during earnings season.
- **Data Source:** Earnings call transcripts, NLP analysis
- **Timeframe Relevance:** During earnings season (4x/year)
- **Priority for 0DTE:** LOW (earnings season-specific)
- **Calculation:** NLP sentiment score on call transcripts

### 8.15 Volume at Ask vs. Volume at Bid (Aggressive Trading Direction)
- **Category:** Sentiment / Positioning / Order Flow
- **Description:** Cumulative volume executed at ask (aggressive buys) vs. cumulative volume at bid (aggressive sells). Ratio >1.5 = strong aggressive buying; <0.67 = strong selling pressure.
- **Data Source:** ThetaData (tick-level classification)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** HIGH
- **Calculation:** ask_volume / bid_volume over period

---

## 9. Regime Detection

### 9.1 Trend Regime (Uptrend vs. Downtrend)
- **Category:** Regime Detection
- **Description:** Binary flag: price above 200-SMA = uptrend; below = downtrend. Filters for directional bias. Defines regime for strategy selection.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Daily, applies intraday
- **Priority for 0DTE:** HIGH
- **Calculation:** 200-SMA; compare to price

### 9.2 Volatility Regime (Low Vol vs. High Vol)
- **Category:** Regime Detection
- **Description:** VIX level classification: VIX <12 = low vol/complacency; 12-20 = normal; 20-30 = elevated; >30 = high vol/stress. Each regime has different dynamics.
- **Data Source:** ThetaData (VIX real-time)
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** VIX thresholds

### 9.3 Range vs. Trend Regime (ADX - Average Directional Index)
- **Category:** Regime Detection
- **Description:** ADX measures trend strength (0-100 scale). ADX >25 = strong trend; <25 = range/choppy. Guides strategy suitability (trend-follow vs. mean-revert).
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** ADX = SMA(+DI - -DI) where ±DI = directional indicators

### 9.4 Volatility Expansion vs. Contraction (Keltner Squeeze)
- **Category:** Regime Detection
- **Description:** Detection of volatility compression (Keltner bands narrow) followed by breakout (Keltner bands expand). Squeeze = low volatility setup; expansion = breakout follow-through.
- **Data Source:** Alpaca (OHLCV)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Keltner band width comparison

### 9.5 Risk-On vs. Risk-Off Sentiment (Market Structure)
- **Category:** Regime Detection / Sentiment
- **Description:** Composite regime: risk-on (broad market strength, low VIX, spreads tight) vs. risk-off (market weak, VIX elevated, spreads wide). Determines expected move direction.
- **Data Source:** Multiple indicators (VIX, breadth, spreads, correlation)
- **Timeframe Relevance:** Daily, intraday
- **Priority for 0DTE:** HIGH
- **Calculation:** Multi-factor regime classification

### 9.6 Gamma Regime (Short Gamma vs. Long Gamma)
- **Category:** Regime Detection / Options Market
- **Description:** When dealers are short gamma (GEX negative), market is unstable (accelerating moves); when dealers long gamma (GEX positive), market is stable. Determines expected volatility level.
- **Data Source:** ThetaData (GEX calculation)
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** GEX sign; magnitude indicates strength

### 9.7 Pinning vs. Free Float Regime (Options Expiration Effect)
- **Category:** Regime Detection / Options Market
- **Description:** Near expiration, market "pins" to max pain strike (dealers defend); far from expiration, market freely moves. Critical for 0DTE: final hours = strong pinning bias.
- **Data Source:** ThetaData (option open interest, price action)
- **Timeframe Relevance:** Daily, critical in final hours of 0DTE
- **Priority for 0DTE:** HIGH
- **Calculation:** Distance to max pain; pin probability increases as days to expiration approach zero

### 9.8 Overnight Session Impact (Futures Gap)
- **Category:** Regime Detection
- **Description:** Large overnight gaps (ES futures after-hours) predict intraday dynamics. Gap up = upside bias until filled; gap down = downside bias. Gap fill probability >70%.
- **Data Source:** Alpaca (open vs. prev close), CME futures
- **Timeframe Relevance:** Opening hours of regular session
- **Priority for 0DTE:** MEDIUM
- **Calculation:** |open - prev_close|; direction

### 9.9 Mean Reversion vs. Momentum Regime
- **Category:** Regime Detection
- **Description:** Detect if market is mean-reverting (price reverts to moving average; high RSI followed by reversal) vs. momentum-driven (price extends from MA; acceleration continues). Changes strategy focus.
- **Data Source:** Alpaca (OHLCV, RSI, price vs. SMA)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Correlation of price moves vs. mean and acceleration

### 9.10 Correlation Regime (Correlations Tightening vs. Loosening)
- **Category:** Regime Detection / Intermarket
- **Description:** When major indices correlations increase (e.g., QQQ, DIA, IWM all move together), systematic risk dominates (likely broad selloff or rally); when correlations loosen, selectivity increases.
- **Data Source:** Alpaca
- **Timeframe Relevance:** Daily, rolling window
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Correlation matrix of major indices; track changes

### 9.11 Liquidity Regime (Tightness of Spreads)
- **Category:** Regime Detection / Market Microstructure
- **Description:** When spreads are tight (< 0.2%), liquidity is abundant; when spreads widen (> 0.5%), liquidity is scarce. Liquidity regime changes impact execution and volatility.
- **Data Source:** ThetaData (spread tracking)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Bid-ask spread percentage; classify into regimes

### 9.12 Market Structure State (VWAP Cross)
- **Category:** Regime Detection / Price Structure
- **Description:** Price above VWAP = market buying structure; below VWAP = selling structure. Flip-flopping indicates accumulation/distribution regime shift.
- **Data Source:** ThetaData, Alpaca
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Price vs. VWAP crossing

---

## 10. Exotic / Specialized Metrics

### 10.1 Entropy (Information Content)
- **Category:** Market Microstructure / Advanced
- **Description:** Shannon entropy of price changes (randomness measure). High entropy = high uncertainty (random walk); low entropy = predictable (mean reversion or trend). Distinguishes noise from signal.
- **Data Source:** Calculated from price data
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** LOW (research-grade metric)
- **Calculation:** Entropy = -Σ(p[i] × log(p[i])) where p[i] = proportion of returns in bin i

### 10.2 Hurst Exponent (Self-Affinity / Mean Reversion Detection)
- **Category:** Market Microstructure / Advanced
- **Description:** Measure of trending vs. mean reverting behavior. H < 0.5 = mean reverting; H = 0.5 = random walk; H > 0.5 = trending. Guides strategy selection.
- **Data Source:** Calculated from price data (requires 100+ points)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Complex; fit to log(range) vs. log(period)

### 10.3 Fractal Dimension
- **Category:** Market Microstructure / Advanced
- **Description:** Complexity of price path. Lower fractal dimension = smoother moves; higher = choppy/noisy. Helps identify when moves are "clean" vs. noisy.
- **Data Source:** Calculated from price data
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** LOW (research-grade)
- **Calculation:** Fractal dimension = 2 - (log(N) / log(D))

### 10.4 Lyapunov Exponent (Chaos Detection)
- **Category:** Market Microstructure / Advanced
- **Description:** Positive Lyapunov = chaotic behavior (diverging paths); negative = stable (converging paths). Detects market breakdowns (chaos) vs. stability.
- **Data Source:** Calculated from price data
- **Timeframe Relevance:** Daily, multi-day windows
- **Priority for 0DTE:** LOW (theoretical, hard to apply intraday)
- **Calculation:** Advanced nonlinear dynamics; typically academic use

### 10.5 Microstructure Noise (Bid-Ask Bounce)
- **Category:** Market Microstructure
- **Description:** Statistical noise from bid-ask bounce (prices alternating between bid/ask randomly). High microstructure noise = signal degradation; should reduce confidence in short-term moves.
- **Data Source:** ThetaData (tick-level prices)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Variance decomposition; estimate noise component

### 10.6 Realized Quarticity (Jump Component Estimation)
- **Category:** Volatility / Advanced
- **Description:** Fourth moment of returns; estimates presence of jumps vs. Brownian motion. High quarticity = jump risk present; low = smooth diffusion. Predicts large intraday moves.
- **Data Source:** Calculated from high-frequency returns
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** LOW (advanced volatility research)
- **Calculation:** RQ = (N/3) × Σ(ret[i]^4) / (RV^2)

### 10.7 Cross-Impact (Price Impact of Trades Across Spreads)
- **Category:** Market Microstructure / Order Flow
- **Description:** How much a large trade on one side impacts the opposite side (e.g., large buy order causes ask to move up). Assesses liquidity resilience.
- **Data Source:** ThetaData (order book reconstruction + trades)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Regression of price impact vs. order size and sign

### 10.8 Bid-Ask Slope (Liquidity Gradient)
- **Category:** Market Microstructure
- **Description:** How quickly bid/ask improves deeper in book (bid increases, ask decreases with depth). Steep slope = thin liquidity; shallow = abundant. Predicts slippage for large orders.
- **Data Source:** ThetaData (level 2/3 data)
- **Timeframe Relevance:** Tick-level, 1min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Regression of bid/ask levels vs. cumulative depth

### 10.9 Roll Model (Price Impact + Inventory Costs)
- **Category:** Market Microstructure
- **Description:** Decomposes bid-ask spread into adverse selection (information leakage) vs. inventory cost components. High adverse selection = informed traders present.
- **Data Source:** ThetaData (spread and quote data)
- **Timeframe Relevance:** 1min, 5min
- **Priority for 0DTE:** LOW (academic model)
- **Calculation:** Complex; requires spread decomposition regression

### 10.10 Kyle Lambda (Price Elasticity of Liquidity)
- **Category:** Market Microstructure / Advanced
- **Description:** How much price moves per unit volume (slope of impact function). High lambda = price moves more per share (illiquid); low lambda = large volume needed to move price (liquid). Guides order sizing.
- **Data Source:** ThetaData (calculated from order impact analysis)
- **Timeframe Relevance:** Intraday rolling window
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Regression of price change vs. signed volume

### 10.11 Intraday Seasonality (Minute of Day Pattern)
- **Category:** Time / Calendar / Advanced
- **Description:** Repeatable patterns in volatility, volume, or returns by minute of day (e.g., minute 1 = high vol; minute 150 = low vol; minute 390 = power hour = high vol). Exploit mechanical patterns.
- **Data Source:** Alpaca (historical data analysis)
- **Timeframe Relevance:** Minute-level, all day
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Aggregate statistics by minute-of-day across 100+ sessions

### 10.12 Correlation with VIX (Beta to Vol)
- **Category:** Volatility / Intermarket
- **Description:** Rolling correlation or beta of SPY returns to VIX changes. Typically negative (stocks down = VIX up). Breakdown = regime shift. Useful for options positioning.
- **Data Source:** ThetaData (VIX), Alpaca (SPY)
- **Timeframe Relevance:** Daily, rolling 20-day window
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Beta(SPY_returns, VIX_changes)

### 10.13 Gamma Ladder (Aggregated Gamma Exposure by Strike)
- **Category:** Options Market / Advanced
- **Description:** Pin-down gamma exposure at each strike level. Identifies strikes where dealers have concentrated gamma (sticky levels) vs. distributed gamma (slippery levels).
- **Data Source:** ThetaData (option greeks by strike)
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH (critical for 0DTE support/resistance)
- **Calculation:** Aggregate gamma across all expirations at each strike

### 10.14 DEX Ladder (Delta Exposure by Strike)
- **Category:** Options Market / Advanced
- **Description:** Delta exposure at each strike. Helps identify support (dealer short delta, buys dips) vs. resistance (dealer long delta, sells rallies). Maps directional pressure zones.
- **Data Source:** ThetaData (option positions)
- **Timeframe Relevance:** Daily, intraday updates
- **Priority for 0DTE:** HIGH
- **Calculation:** Aggregate dealer delta across all expirations at each strike

### 10.15 Volatility-Adjusted Returns (Risk-Adjusted Performance)
- **Category:** Volatility / Price Structure
- **Description:** Current intraday return divided by realized volatility (risk-adjusted return). High ratio = move is strong relative to volatility; low = weak move. Assesses conviction.
- **Data Source:** Alpaca (returns, volatility)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** (price - open) / RV

### 10.16 Order Book Reconstruction (Hidden Liquidity)
- **Category:** Market Microstructure / Advanced
- **Description:** Real-time tracking of executed orders vs. visible order book. Detects hidden/iceberg orders and dark pool activity. Assesses true available liquidity.
- **Data Source:** ThetaData (level 2/3 + block trades)
- **Timeframe Relevance:** Tick-level
- **Priority for 0DTE:** MEDIUM
- **Calculation:** Compare executed volume to posted volume

### 10.17 Vanna Ladder (Vanna by Strike)
- **Category:** Options Market / Advanced
- **Description:** Vanna aggregated by strike. Helps predict how gamma hedging flows respond to market movement direction. Vanna reversal predicts flow direction changes.
- **Data Source:** ThetaData (option greeks by strike)
- **Timeframe Relevance:** Daily, intraday
- **Priority for 0DTE:** HIGH
- **Calculation:** Aggregate vanna across all expirations by strike

### 10.18 Charm Ladder (Charm by Strike)
- **Category:** Options Market / Advanced
- **Description:** Charm concentrated by strike. Near 0DTE expiration, charm spikes dramatically at strikes with high open interest, predicting final hour rotation.
- **Data Source:** ThetaData (option greeks by strike)
- **Timeframe Relevance:** Intraday, especially final hours of 0DTE
- **Priority for 0DTE:** HIGH
- **Calculation:** Aggregate charm across all expirations by strike

### 10.19 Gamma Convexity (2nd Derivative of Gamma)
- **Category:** Options Market / Advanced
- **Description:** Rate of change of gamma (gamma's gamma). High convexity = gamma changes rapidly as price moves; indicates "pinning" zones where gamma acceleration is extreme.
- **Data Source:** ThetaData (calculated from successive gamma values)
- **Timeframe Relevance:** 5min, 15min
- **Priority for 0DTE:** MEDIUM
- **Calculation:** dGamma = Gamma[t] - Gamma[t-1]

### 10.20 Options Implied Move (Straddle Price)
- **Category:** Options Market / Volatility
- **Description:** Inferred expected move from ATM straddle price. Straddle value = (IV × stock_price × sqrt(T) × 0.4) approximately. Markets prices expected move magnitude.
- **Data Source:** ThetaData (ATM option prices, calculated)
- **Timeframe Relevance:** Daily, real-time updates
- **Priority for 0DTE:** HIGH
- **Calculation:** ATM straddle price / stock price; or IV-derived expected move

---

## Summary Table: Prioritization Guide for 0DTE Bot Development

| Priority | Category | Key Metrics (Top 20) |
|----------|----------|----------------------|
| **HIGH** | Order Flow | CVD, VWAP, aggressive buy ratio, block absorption, sweeps, 5-min delta, imbalance ratio, BA imbalance, VPIN, toxicity |
| **HIGH** | Volatility | VIX, realized vol, IV skew, IV term structure, TR expansion, RV/IV ratio |
| **HIGH** | Options Greeks | GEX, DEX, Put/Call ratio (volume), Max Pain, delta rehedging, charm, vanna, dealer gamma, option OI ladder |
| **HIGH** | Price Structure | HOD/LOD distance, VWAP deviation, SMA 20, Pivots, volume-based S/R, trend direction, Bollinger Bands |
| **HIGH** | Time-Based | Time since open, time until close, opening 30min, power hour, expiration week, FOMC days, final hour charm spike |
| **HIGH** | Intermarket | QQQ vs. SPY, NYSE TICK, ES futures leading, Breadth/A-D line, bid-ask spreads |
| **HIGH** | Gamma Regime | GEX sign (dealers short gamma = volatile), DEX positioning, gamma ladder, charm acceleration |
| **HIGH** | 0DTE Specific | Max pain, charm acceleration in final hours, vanna ladder, gamma ladder, DEX ladder |
| **MEDIUM** | Order Flow | OBV, MFI, dark pool imbalance, sweep confirmation, order book imbalance, point of control |
| **MEDIUM** | Volatility | VVIX, vol clustering, vol half-life, gap size, Parkinson vol, historical/realized vol |
| **MEDIUM** | Options Greeks | Put skew, call skew, vega exposure, put/call OI, implied skew/kurtosis |
| **MEDIUM** | Price Structure | RSI, Bollinger Bands %B, Keltner channels, Fibonacci levels, market profile, linear regression, price patterns |
| **MEDIUM** | Time-Based | Day of week, lunch hour, Monday gaps, earning season, EOM/EOQ, after-hours ES, vol half-life |
| **MEDIUM** | Sentiment | Put/call premium, call spread vs. put spread, flow skewness, Fear & Greed index, leveraged ETF flows |
| **MEDIUM** | Microstructure | Spread width volatility, order depth (bid/ask), participation rate, trade size concentration, liquidity regime |

---

## Data Capture Architecture Recommendations

### Primary Data Sources
1. **ThetaData** - tick-level tape, order flow, options chains, greeks
2. **Alpaca** - OHLCV, real-time quotes, options
3. **External Feeds** - VIX (CBOE), ES futures (CME), economic calendar

### Sampling Strategy
- **Tick-level:** CVD, VWAP, imbalance ratio, block absorption, sweep detection
- **1-min bars:** Volatility, volume patterns, momentum
- **5-min bars:** Price structure, VWAP deviation, moving averages, gamma ladder updates
- **Daily:** Regime classification, weekly rolling stats

### Storage & Computation
- Real-time metrics: In-memory state machines
- Historical metrics: Time-series database (InfluxDB, Parquet)
- Calculations: NumPy/Pandas for efficiency

---

## References & Further Reading

- Easley, D., López de Prado, M. M., & O'Hara, M. (2012). "The Volume Clock." *The Journal of Portfolio Management*.
- Gatheral, J. (2006). *The Volatility Surface*. Wiley.
- López de Prado, M. M. (2018). *Advances in Financial Machine Learning*. Wiley.
- Nassar, S. (2014). *Options Spread Trading*. Wiley (gamma/vanna application).
- Rissanen, J. (1989). *Stochastic Complexity in Statistical Inquiry*. World Scientific (entropy in markets).

---

**Document Version:** 1.0
**Last Updated:** 2026-03-31
**Author Notes:** This document synthesizes industry-standard metrics from academic literature, prop trading practices (particularly Citadel, Jump Trading, DRW), and options market microstructure research. Prioritization reflects 0DTE-specific dynamics where gamma, charm, and pinning effects dominate intraday price movement. Metrics should be incorporated incrementally, starting with HIGH priority items.

