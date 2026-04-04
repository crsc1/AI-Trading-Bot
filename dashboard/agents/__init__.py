"""
Multi-Agent Orchestration System for SPY 0DTE Options Trading.

Architecture:
  5 specialized agents, each running on independent polling cycles,
  feeding into a central SignalPublisher that produces trade signals
  only when multiple agents agree.

Agents:
  1. PriceFlowAgent      — Order flow, CVD, absorption, large trades (rule-based)
  2. NewsAgent            — Real-time news from Alpaca + Finnhub (LLM-interpreted)
  3. SentimentAgent       — Reddit, Fear & Greed, VIX regime (hybrid)
  4. MarketStructureAgent — VWAP, levels, pivots, session context (rule-based)
  5. SignalPublisher      — Orchestrates agents, publishes signals, tracks P/L
"""
