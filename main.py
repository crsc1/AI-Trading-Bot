"""
SPX/SPY OPTIONS TRADING BOT - Main Entry Point
================================================

Connects all pieces together:
  1. Data providers: ThetaData (options/EOD) + Alpaca (real-time trades, SIP)
  2. Strategies (analyzing data and generating signals)
  3. Signal aggregator (combining signals into recommendations)
  4. Risk manager (making sure we don't lose too much)
  5. Dashboard (web UI for viewing signals and managing trades)

HOW TO RUN:
  python main.py                  # Run in SIGNAL mode (default, safest)
  python main.py --mode semi_auto # Run with trade approval
  python main.py --mode auto      # Full automation (careful!)
  python main.py --paper          # Paper trading (simulated, no real money)
"""

import asyncio
import argparse
import signal
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

# ============================================================================
# Add project root to Python path so imports work
# ============================================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Load .env file into os.environ so all modules can access API keys
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ============================================================================
# Import our modules
# ============================================================================
from config.settings import settings
from utils.logger import get_logger
from data.cache import Cache
from data.storage import Database as Storage

# Data providers — ThetaData + Alpaca only
from data.providers.alpaca import AlpacaDataProvider as AlpacaProvider

# Engine components
from engine.signal_aggregator import SignalAggregator
from engine.risk_manager import RiskManager
from engine.probability import ProbabilityEngine
from engine.pattern_analyzer import PatternAnalyzer
from engine.market_context import MarketContext

# Strategies
from strategies.directional import DirectionalStrategy
from strategies.opening_range import OpeningRangeBreakout
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.credit_spreads import CreditSpreadStrategy
from strategies.flow_based import FlowBasedStrategy

# ============================================================================
# Setup logger
# ============================================================================
logger = get_logger("main")


class TradingBot:
    """
    Main trading bot — orchestrates data fetching, strategy analysis,
    signal aggregation, and risk management each cycle.

    Data sources:
      - Alpaca Algo Trader Plus: real-time SIP trades, snapshots, historical bars
      - ThetaData Terminal: options chains, greeks, OI, EOD stock bars
    """

    def __init__(self, mode: str = "SIGNAL", paper: bool = True):
        self.mode = mode.upper()
        self.paper = paper
        self.running = False
        self.cycle_count = 0

        # Core components
        self.cache = Cache()
        self.storage = Storage(settings.database_path)

        # Data providers
        self.providers: Dict[str, Any] = {}
        self._init_providers()

        # Strategies
        self.strategies: List[Any] = []
        self._init_strategies()

        # Engine components
        self.signal_aggregator = SignalAggregator()
        self.risk_manager = RiskManager(account_balance=settings.starting_capital)
        self.probability = ProbabilityEngine()
        self.pattern_analyzer = PatternAnalyzer()
        self.market_context = MarketContext()

        # Dashboard WebSocket broadcast function (set at startup)
        self.broadcast_signal = None

        logger.info("=" * 60)
        logger.info("SPX/SPY OPTIONS TRADING BOT INITIALIZED")
        logger.info(f"  Mode: {self.mode}")
        logger.info(f"  Paper Trading: {self.paper}")
        logger.info(f"  Capital: ${settings.starting_capital:,.2f}")
        logger.info(f"  Max Risk/Trade: {settings.max_risk_per_trade * 100}%")
        logger.info(f"  Strategies: {len(self.strategies)}")
        logger.info(f"  Symbols: {settings.trading_symbols}")
        logger.info("  Data: Alpaca SIP + ThetaData")
        logger.info("=" * 60)

    def _init_providers(self):
        """Initialize data providers: Alpaca (real-time + bars) + ThetaData (options)."""

        # Alpaca Algo Trader Plus — SIP real-time trades + historical
        if settings.alpaca_api_key and settings.alpaca_secret_key:
            self.providers["alpaca"] = AlpacaProvider(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
            )
            logger.info(f"Alpaca provider initialized (feed={settings.alpaca_data_feed})")
        else:
            logger.warning("No Alpaca API keys — real-time market data unavailable")

        # ThetaData is accessed via HTTP to localhost:25503 (Theta Terminal)
        # No provider class needed — dashboard api_routes.py calls it directly
        if settings.theta_enabled:
            logger.info(f"ThetaData enabled at {settings.theta_base_url}")
        else:
            logger.warning("ThetaData disabled — options data unavailable")

        if not self.providers:
            logger.error("NO DATA PROVIDERS CONFIGURED!")
            logger.error("Please add Alpaca API keys to your .env file")

    def _init_strategies(self):
        """Initialize all trading strategies with their weights."""
        self.strategies = [
            DirectionalStrategy(name="Directional", weight=settings.weight_technical),
            OpeningRangeBreakout(name="OpeningRange", weight=0.20),
            MomentumStrategy(name="Momentum", weight=0.15),
            MeanReversionStrategy(name="MeanReversion", weight=0.15),
            CreditSpreadStrategy(name="CreditSpread", weight=0.10),
            FlowBasedStrategy(name="FlowBased", weight=settings.weight_flow_analysis),
        ]
        logger.info(f"Initialized {len(self.strategies)} strategies:")
        for s in self.strategies:
            logger.info(f"  - {s.name} (weight: {s.weight})")

    async def fetch_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch all available market data for a symbol.

        Sources:
          1. Alpaca snapshot (latest trade, quote, bars) — real-time SIP
          2. ThetaData options data is fetched separately by the dashboard
        """
        market_data: Dict[str, Any] = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "price": {},
            "options": {},
            "news": [],
            "sentiment": {},
            "flow": {},
            "calendar": {},
            "technicals": {},
        }

        # Check cache first
        cached = self.cache.get(f"market_data_{symbol}")
        if cached:
            return cached

        # Alpaca — real-time price + historical bars
        if "alpaca" in self.providers:
            try:
                alpaca = self.providers["alpaca"]

                # Snapshot: latest trade, quote, minute bar, daily bar
                snapshot = await alpaca.fetch_snapshot(symbol)
                if snapshot:
                    if snapshot.get("last_trade"):
                        market_data["price"] = {
                            "symbol": symbol,
                            "price": snapshot["last_trade"]["price"],
                            "source": "alpaca_sip",
                        }
                    market_data["alpaca_snapshot"] = snapshot

                # Historical bars for technical analysis
                bars = await alpaca.fetch_historical_bars(
                    symbol, timeframe="5Min", limit=100
                )
                if bars:
                    market_data["technicals"]["bars"] = bars

            except Exception as e:
                logger.error(f"Alpaca data fetch failed for {symbol}: {e}")

        # Cache the combined data
        self.cache.set(
            f"market_data_{symbol}",
            market_data,
            ttl_seconds=settings.cache_ttl_seconds,
        )

        return market_data

    async def run_analysis_cycle(self):
        """
        Run one complete analysis cycle (every ~60s during market hours).

        1. Fetch fresh data for each symbol
        2. Determine market context
        3. Run all strategies
        4. Aggregate signals
        5. Check risk rules
        6. Output recommendation
        """
        self.cycle_count += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"ANALYSIS CYCLE #{self.cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"{'='*60}")

        for symbol in settings.trading_symbols:
            try:
                logger.info(f"\n--- Analyzing {symbol} ---")
                market_data = await self.fetch_market_data(symbol)

                context = self.market_context.get_context_summary()
                if self.market_context.is_high_risk_period():
                    logger.warning("HIGH RISK PERIOD detected — reducing position sizes")
                    context["high_risk"] = True

                # Run strategies
                signals = []
                for strategy in self.strategies:
                    try:
                        sig = await strategy.analyze(
                            market_data=market_data,
                            options_data=market_data.get("options", {}),
                            context=context,
                        )
                        if sig:
                            signals.append(sig)
                            logger.info(
                                f"  [{strategy.name}] {sig.recommended_action} "
                                f"| Score: {sig.score:+.0f} "
                                f"| Confidence: {sig.confidence:.0%}"
                            )
                    except Exception as e:
                        logger.error(f"Strategy {strategy.name} failed: {e}")

                if not signals:
                    logger.info(f"  No signals generated for {symbol}")
                    continue

                # Aggregate
                recommendation = self.signal_aggregator.aggregate(signals)
                if recommendation is None:
                    logger.info("  Aggregator: NO TRADE (signals too weak or conflicting)")
                    continue

                # Probability and expected value
                win_prob = self.probability.calculate_win_probability(recommendation)
                ev = self.probability.calculate_expected_value(recommendation)

                logger.info(f"\n  RECOMMENDATION: {recommendation.recommended_action}")
                logger.info(f"  Strike: {recommendation.strike} | Expiry: {recommendation.expiry}")
                logger.info(f"  Entry: ${recommendation.entry_price:.2f} | Stop: ${recommendation.stop_loss:.2f} | Target: ${recommendation.profit_target:.2f}")
                logger.info(f"  Confidence: {recommendation.confidence:.0%} | Win Prob: {win_prob:.0%} | EV: ${ev:.2f}")

                # Risk check
                allowed, reason = self.risk_manager.check_trade_allowed(recommendation)
                if not allowed:
                    logger.warning(f"  BLOCKED by Risk Manager: {reason}")
                    continue

                position_size = self.risk_manager.calculate_position_size(
                    recommendation, settings.starting_capital
                )
                logger.info(f"  Position Size: {position_size} contracts")

                # Save to DB
                await self.storage.save_signal(
                    ticker=recommendation.symbol,
                    signal_type=recommendation.recommended_action,
                    strength=recommendation.score,
                    indicators={
                        "direction": recommendation.direction,
                        "strategy": recommendation.strategy,
                        "confidence": recommendation.confidence,
                        "strike": recommendation.strike,
                        "expiry": recommendation.expiry,
                        "risk_reward": recommendation.risk_reward,
                    },
                    entry_price=recommendation.entry_price,
                    target_price=recommendation.profit_target,
                    stop_loss=recommendation.stop_loss,
                    notes=recommendation.reasoning,
                )

                # Handle based on mode
                if self.mode == "AUTO" and not self.paper:
                    logger.info("  AUTO MODE: Would execute trade (broker integration pending)")
                elif self.mode == "SEMI_AUTO":
                    logger.info("  SEMI-AUTO: Signal sent to dashboard for approval")
                else:
                    logger.info("  SIGNAL MODE: Recommendation logged and displayed")

                # Broadcast to dashboard
                if self.broadcast_signal:
                    await self.broadcast_signal({
                        "type": "new_signal",
                        "signal": {
                            "symbol": recommendation.symbol,
                            "action": recommendation.recommended_action,
                            "strike": recommendation.strike,
                            "expiry": recommendation.expiry,
                            "confidence": recommendation.confidence,
                            "entry": recommendation.entry_price,
                            "stop_loss": recommendation.stop_loss,
                            "target": recommendation.profit_target,
                            "reasoning": recommendation.reasoning,
                            "win_probability": win_prob,
                            "position_size": position_size,
                        },
                    })

            except Exception as e:
                logger.error(f"Analysis cycle failed for {symbol}: {e}")
                import traceback
                traceback.print_exc()

    def is_market_hours(self) -> bool:
        """Check if we're within trading hours (weekdays, 9:45-15:30 ET)."""
        now = datetime.now()
        if now.weekday() > 4:
            return False
        return settings.trading_start_time <= now.time() <= settings.trading_end_time

    async def run(self):
        """Main run loop — analysis cycles during market hours."""
        self.running = True
        await self.storage.connect()

        for name, provider in self.providers.items():
            logger.info(f"Provider {name} ready")

        logger.info("\nTrading bot is RUNNING. Press Ctrl+C to stop.")
        logger.info(f"Dashboard: http://localhost:{settings.dashboard_port}")

        try:
            while self.running:
                if self.is_market_hours():
                    await self.run_analysis_cycle()
                else:
                    logger.debug(
                        f"Outside market hours ({datetime.now().strftime('%H:%M')}). "
                        f"Checking again in 5 minutes..."
                    )
                wait_time = 60 if self.is_market_hours() else 300
                await asyncio.sleep(wait_time)
        except asyncio.CancelledError:
            logger.info("Bot shutting down...")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Clean shutdown — close all connections."""
        self.running = False
        logger.info("Shutting down trading bot...")

        for name, provider in self.providers.items():
            try:
                await provider.close()
                logger.info(f"Provider {name} disconnected")
            except Exception as e:
                logger.error(f"Error closing {name}: {e}")

        await self.storage.disconnect()
        logger.info("Trading bot stopped. Goodbye!")


# ============================================================================
# DASHBOARD INTEGRATION
# ============================================================================

async def run_with_dashboard(bot: TradingBot):
    """Run bot alongside the FastAPI web dashboard."""
    import uvicorn
    from dashboard.app import app

    app.state.bot = bot

    config = uvicorn.Config(
        app=app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        bot.run(),
    )


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="SPX/SPY Options Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Signal mode (default)
  python main.py --mode semi_auto   # Semi-auto with approval
  python main.py --mode auto        # Full automation
  python main.py --paper            # Paper trading
  python main.py --no-dashboard     # Bot only, no web UI
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["signal", "semi_auto", "auto"],
        default="signal",
        help="Trading mode",
    )
    parser.add_argument("--paper", action="store_true", default=True)
    parser.add_argument("--live", action="store_true", default=False)
    parser.add_argument("--no-dashboard", action="store_true", default=False)

    return parser.parse_args()


def main():
    args = parse_args()

    paper = not args.live
    if args.live:
        print("\n" + "!" * 60)
        print("WARNING: LIVE TRADING MODE")
        print("You are about to trade with REAL MONEY.")
        print("!" * 60)
        confirm = input("\nType 'YES I UNDERSTAND' to continue: ")
        if confirm != "YES I UNDERSTAND":
            print("Live trading cancelled. Running in paper mode instead.")
            paper = True

    bot = TradingBot(mode=args.mode, paper=paper)

    def signal_handler(sig, frame):
        print("\nShutting down... (press Ctrl+C again to force quit)")
        bot.running = False

    signal.signal(signal.SIGINT, signal_handler)

    if args.no_dashboard:
        asyncio.run(bot.run())
    else:
        asyncio.run(run_with_dashboard(bot))


if __name__ == "__main__":
    main()
