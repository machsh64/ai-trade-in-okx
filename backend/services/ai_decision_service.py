"""
AI Decision Service - Handles AI model API calls for trading decisions
"""
import logging
import random
import json
import time
from decimal import Decimal
from typing import Dict, Optional, List

import requests
from sqlalchemy.orm import Session

from database.models import Position, Account, AIDecisionLog
from services.asset_calculator import calc_positions_value
from services.news_feed import fetch_latest_news


logger = logging.getLogger(__name__)

#  mode API keys that should be skipped
DEMO_API_KEYS = {
    "default-key-please-update-in-settings",
    "default",
    "",
    None
}

SUPPORTED_SYMBOLS: Dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "DOGE": "Dogecoin",
    "XRP": "Ripple",
    "BNB": "Binance Coin",
}


def _is_default_api_key(api_key: str) -> bool:
    """Check if the API key is a default/placeholder key that should be skipped"""
    return api_key in DEMO_API_KEYS


def _get_portfolio_data_from_okx(account: Account = None) -> Dict:
    """
    从OKX获取真实账户数据（用于AI决策）
    Get real OKX account data for AI trading decisions
    
    Args:
        account: Account model instance with OKX credentials (optional)
                If not provided and no .env config, will raise error
    """
    try:
        from services.okx_market_data import fetch_balance_okx, fetch_positions_okx
        
        # 获取OKX余额（传入account使用其配置）
        balance = fetch_balance_okx(account=account)
        
        # CCXT返回的格式:
        # balance['info']['data'][0]['totalEq'] = 总权益
        # balance['USDT']['free'] = USDT可用余额
        # balance['total']['USDT'] = USDT总额
        
        usdt_free = float(balance.get('USDT', {}).get('free', 0))  # USDT可用余额
        usdt_total = float(balance.get('USDT', {}).get('total', 0))  # USDT总额
        usdt_used = float(balance.get('USDT', {}).get('used', 0))  # USDT占用（冻结）
        
        # 如果没有top-level的余额信息，从info中提取
        if usdt_total == 0 and 'info' in balance:
            info_data = balance['info'].get('data', [])
            if info_data:
                account_data = info_data[0]
                # totalEq是总权益（USDT计价）
                usdt_total = float(account_data.get('totalEq', 0))
                # 从details中找USDT的详细信息
                for detail in account_data.get('details', []):
                    if detail.get('ccy') == 'USDT':
                        usdt_free = float(detail.get('availBal', 0))
                        usdt_used = float(detail.get('frozenBal', 0))
                        break
        
        # 获取OKX持仓（传入account使用其配置）
        positions = fetch_positions_okx(account=account)
        portfolio = {}
        total_position_value = 0.0
        
        for pos in positions:
            symbol = pos.get('symbol', '').replace('/USDT:USDT', '')  # BTC/USDT:USDT -> BTC
            if not symbol:
                continue
                
            quantity = abs(float(pos.get('contracts', 0)))  # 持仓数量
            if quantity > 0:
                entry_price = float(pos.get('entryPrice', 0))  # 开仓均价
                notional = abs(float(pos.get('notional', 0)))  # 持仓价值
                leverage_raw = pos.get('leverage', 1)  # 杠杆倍数
                margin_mode = pos.get('marginMode', 'cross')  # 保证金模式
                # 持仓方向: CCXT可能返回'side'或'posSide'字段
                side = pos.get('side') or pos.get('posSide') or 'long'
                
                # 解析杠杆（可能是字符串）
                try:
                    leverage = float(leverage_raw) if leverage_raw else 1
                except:
                    leverage = 1
                
                portfolio[symbol] = {
                    "quantity": quantity,
                    "avg_cost": entry_price,
                    "current_value": notional,
                    "leverage": int(leverage),
                    "margin_mode": margin_mode,
                    "side": side  # 持仓方向: 'long' 或 'short'
                }
                total_position_value += notional
        
        logger.info(f"[OKX Portfolio] Cash=${usdt_free:.2f}, Frozen=${usdt_used:.2f}, Positions=${total_position_value:.2f}, Total=${usdt_total:.2f}")
        print(f"[OKX Portfolio] Cash=${usdt_free:.2f}, Frozen=${usdt_used:.2f}, Positions=${total_position_value:.2f}, Total=${usdt_total:.2f}")
        
        return {
            "cash": usdt_free,
            "frozen_cash": usdt_used,
            "positions": portfolio,
            "total_assets": usdt_total
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to get OKX portfolio data: {error_msg}")
        
        # 如果是OKX凭证未配置的错误，给出更友好的提示
        if "Private API not initialized" in error_msg or "check OKX credentials" in error_msg:
            logger.warning("⚠️ OKX credentials not configured for this account. Please configure OKX API credentials in Account Management.")
            # 返回空数据，让系统可以继续运行（但不会进行交易）
            return {
                "cash": 0.0,
                "frozen_cash": 0.0,
                "positions": {},
                "total_assets": 0.0,
                "error": "OKX_NOT_CONFIGURED"
            }
        
        import traceback
        traceback.print_exc()
        # 其他错误也返回默认数据
        return {
            "cash": 0.0,
            "frozen_cash": 0.0,
            "positions": {},
            "total_assets": 0.0
        }


def _get_portfolio_data(db: Session, account: Account) -> Dict:
    """
    Get current portfolio positions and values
    已废弃：现在AI交易使用OKX真实数据，请使用 _get_portfolio_data_from_okx()
    """
    # 对于AI账户，直接从OKX获取数据（传入account使用其配置）
    if account.account_type == "AI":
        return _get_portfolio_data_from_okx(account=account)
    
    # 对于其他账户类型，使用本地数据库数据（向后兼容）
    positions = db.query(Position).filter(
        Position.account_id == account.id,
        Position.market == "CRYPTO"
    ).all()
    
    portfolio = {}
    for pos in positions:
        if float(pos.quantity) > 0:
            portfolio[pos.symbol] = {
                "quantity": float(pos.quantity),
                "avg_cost": float(pos.avg_cost),
                "current_value": float(pos.quantity) * float(pos.avg_cost)
            }
    
    return {
        "cash": float(account.current_cash),
        "frozen_cash": float(account.frozen_cash),
        "positions": portfolio,
        "total_assets": float(account.current_cash) + calc_positions_value(db, account.id)
    }


def call_ai_for_decision(account: Account, portfolio: Dict, prices: Dict[str, float], db: Session = None) -> Optional[Dict]:
    """Call AI model API to get trading decision"""
    # Check if this is a default API key
    if _is_default_api_key(account.api_key):
        logger.info(f"Skipping AI trading for account {account.name} - using default API key")
        return None
    
    try:
        # 获取当前时间
        from datetime import datetime
        current_time = datetime.utcnow()
        current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # 获取最近5条AI决策记录
        recent_decisions_text = ""
        if db:
            recent_decisions = db.query(AIDecisionLog).filter(
                AIDecisionLog.account_id == account.id
            ).order_by(AIDecisionLog.decision_time.desc()).limit(5).all()
            
            if recent_decisions:
                recent_decisions_text = "\n\nYOUR RECENT TRADING HISTORY (Last 5 decisions):\n"
                recent_decisions_text += "Review your recent trades to avoid overtrading and maintain consistency:\n"
                for i, dec in enumerate(reversed(recent_decisions), 1):  # 从最早到最近
                    time_ago = current_time - dec.decision_time
                    hours_ago = int(time_ago.total_seconds() / 3600)
                    minutes_ago = int((time_ago.total_seconds() % 3600) / 60)
                    time_str = f"{hours_ago}h {minutes_ago}m ago" if hours_ago > 0 else f"{minutes_ago}m ago"
                    
                    recent_decisions_text += f"\n{i}. [{dec.decision_time.strftime('%Y-%m-%d %H:%M UTC')}] ({time_str})\n"
                    recent_decisions_text += f"   Operation: {dec.operation}\n"
                    if dec.symbol:
                        recent_decisions_text += f"   Symbol: {dec.symbol}\n"
                    recent_decisions_text += f"   Target Portion: {float(dec.target_portion):.1%}\n"
                    if dec.leverage and dec.leverage > 1:
                        recent_decisions_text += f"   Leverage: {dec.leverage}x\n"
                    recent_decisions_text += f"   Executed: {'Yes' if dec.executed == 'true' else 'No'}\n"
                    recent_decisions_text += f"   Reason: {dec.reason[:600]}{'...' if len(dec.reason) > 600 else ''}\n"
                
                recent_decisions_text += "\n⚠️ IMPORTANT: Review your recent decisions before making a new one!\n"
                recent_decisions_text += "- Avoid opening and closing positions too frequently (overtrading)\n"
                recent_decisions_text += "- Give your positions time to develop before making changes\n"
                recent_decisions_text += "- Consider if you're being too reactive to short-term noise\n"
                recent_decisions_text += "- Maintain a consistent strategy rather than constantly changing direction\n"
        
        # 获取新闻摘要
        news_summary = fetch_latest_news()
        news_section = news_summary if news_summary else "No recent CoinJournal news available."
        
        # 获取主要币种的市场分析数据（历史价格 + 技术指标）
        from services.okx_market_data import get_market_analysis
        
        symbols_to_analyze = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]
        market_analysis = {}
        
        logger.info("Fetching market analysis data for AI decision...")
        for symbol in symbols_to_analyze:
            try:
                analysis = get_market_analysis(symbol, period="1h", count=168)  # 1周的小时线
                if "error" not in analysis:
                    market_analysis[symbol] = analysis
                    logger.info(f"  - {symbol}: Got {analysis.get('data_points', 0)} data points")
                else:
                    logger.warning(f"  - {symbol}: Failed - {analysis.get('error')}")
            except Exception as e:
                logger.error(f"Failed to get analysis for {symbol}: {e}")
        
        # 构建市场分析摘要文本
        market_analysis_text = ""
        for symbol, analysis in market_analysis.items():
            market_analysis_text += f"\n{symbol} Analysis:\n"
            market_analysis_text += f"  Current Price: ${analysis['current_price']}\n"
            market_analysis_text += f"  Price Changes: 15m:{analysis['price_changes']['15m_percent']}%, "
            market_analysis_text += f"1h:{analysis['price_changes']['1h_percent']}%, "
            market_analysis_text += f"4h:{analysis['price_changes']['4h_percent']}%, "
            market_analysis_text += f"24h:{analysis['price_changes']['24h_percent']}%, "
            market_analysis_text += f"7d:{analysis['price_changes']['7d_percent']}%\n"
            
            if analysis['moving_averages']['sma_7']:
                market_analysis_text += f"  Moving Averages: SMA7=${analysis['moving_averages']['sma_7']}, "
                market_analysis_text += f"SMA25=${analysis['moving_averages']['sma_25']}, "
                market_analysis_text += f"SMA99=${analysis['moving_averages']['sma_99']}\n"
            
            if analysis['technical_indicators']['rsi_14']:
                market_analysis_text += f"  RSI(14): {analysis['technical_indicators']['rsi_14']} "
                rsi = analysis['technical_indicators']['rsi_14']
                if rsi > 70:
                    market_analysis_text += "(OVERBOUGHT)\n"
                elif rsi < 30:
                    market_analysis_text += "(OVERSOLD)\n"
                else:
                    market_analysis_text += "(NEUTRAL)\n"
            
            market_analysis_text += f"  Trend: {analysis['technical_indicators']['trend']}\n"
            market_analysis_text += f"  Volatility(24h): {analysis['technical_indicators']['volatility_24h']}%\n"
            market_analysis_text += f"  Support/Resistance: ${analysis['support_resistance']['recent_low_24h']} / ${analysis['support_resistance']['recent_high_24h']}\n"
            market_analysis_text += f"  Volume Ratio: {analysis['volume_analysis']['volume_ratio']}x (vs 24h avg)\n"
            
            # 添加最近K线趋势
            recent = analysis['recent_candles'][-3:]  # 最近3根K线
            market_analysis_text += f"  Recent Trend (last 3 candles): "
            market_analysis_text += " → ".join([f"{c['change']:+.1f}%" for c in recent])
            market_analysis_text += "\n"

        prompt = f"""You are a professional cryptocurrency FUTURES trading AI with a SHORT-TERM TRADING focus. You trade perpetual futures contracts which allow BOTH long (buy) and short (sell) positions with leverage (1x-50x).

CURRENT TIME: {current_time_str}
{recent_decisions_text}

Portfolio Data:
- Cash Available: ${portfolio['cash']:.2f}
- Frozen Cash (In Orders): ${portfolio['frozen_cash']:.2f}
- Total Assets: ${portfolio['total_assets']:.2f}
- Current Positions: {json.dumps(portfolio['positions'], indent=2)}

Current Market Prices:
{json.dumps(prices, indent=2)}

TECHNICAL ANALYSIS & MARKET DATA (Past 7 Days with 1-hour candles):
{market_analysis_text}

Latest Crypto News (CoinJournal):
{news_section}

YOUR MISSION:
Analyze the market and make SHORT-TERM trading decisions on perpetual futures. You can profit from BOTH rising markets (long positions) AND falling markets (short positions).

🔥 PERPETUAL FUTURES TRADING:
- **LONG positions (buy)**: Profit when price goes UP. Open with "buy_long", close with "close_long"
- **SHORT positions (sell)**: Profit when price goes DOWN. Open with "sell_short", close with "close_short"
- You can hold multiple positions in different coins simultaneously
- Each position can be either LONG or SHORT independently
- Current positions show "side": "long" or "short" to indicate direction

⚠️ SHORT-TERM TRADING STRATEGY:
- PRIMARY: Keep positions for less than 1 WEEK (7 days) in most cases
- ONLY hold longer if you have EXCEPTIONAL confidence in a strong trend
- Focus on capturing short-term momentum and quick profits
- Be ready to close positions quickly if momentum weakens
- Prioritize risk management over long-term holding
- React to short-term price movements (15min, 1h, 4h timeframes)

💡 PORTFOLIO DIVERSIFICATION:
- You CAN hold MULTIPLE different cryptocurrencies SIMULTANEOUSLY
- You can MIX long and short positions (e.g., long BTC + short ETH)
- Don't feel limited to holding only one position at a time
- Diversify across different coins when opportunities arise
- Each coin decision is independent
- Consider spreading risk across 2-3 different positions
- Balance your portfolio based on conviction and market conditions

AVAILABLE TOOLS:
- Leverage: 1x to 50x (higher leverage = higher risk and reward)
- Operations: buy, sell, hold
- Multiple timeframes: 15min, 1h, 4h, 24h, 7d price changes
- Technical indicators: RSI, Moving Averages, Trend, Volume, Volatility
- Market news and sentiment

YOUR DECISION FRAMEWORK:
1. **Market Analysis**: Study all timeframes (15m, 1h, 4h, 24h, 7d) to understand short-term momentum and long-term trends
2. **Technical Signals**: Interpret RSI, moving averages, volume, and volatility in context
3. **Risk Assessment**: Consider volatility and market conditions when choosing leverage
4. **Position Sizing**: Decide how much capital to deploy (0-100% of available cash)
5. **News Impact**: Factor in crypto news sentiment and market events
6. **EXIT PLANNING**: Always consider when to exit - don't let positions sit too long

LEVERAGE GUIDELINES:
- 1-3x: Conservative, suitable for uncertain markets or high volatility
- 4-10x: Moderate, for clear trends with confirmation
- 11-25x: Aggressive, for very strong conviction with multiple confirming signals
- 26-50x: Extreme, only for exceptional opportunities with overwhelming evidence and tight risk management
- Higher leverage amplifies both gains AND losses exponentially
- For short-term trades, higher leverage can be appropriate with tight stops

POSITION MANAGEMENT:
- Check existing positions - if held for 5+ days without strong momentum, consider closing
- If a position shows 15-20% profit in short-term, consider taking profits
- If a position shows 8-10% loss, consider cutting it
- Don't be afraid to sell and re-enter at better prices
- You can manage multiple positions: hold ETH while buying SOL, or sell BTC while keeping DOGE
- Diversification is your friend - don't put all capital in one coin unless extremely confident

⚠️ IMPORTANT - DO NOT OVERTRADE:
- You will be asked for your decision regularly, but you DON'T need to trade every time
- "hold" is a VALID and often WISE choice when market conditions are unclear
- Only trade when you have clear conviction and good entry points
- Quality over quantity - wait for the right opportunities
- Patience is a virtue in trading - don't force trades

MAKE YOUR DECISION - be bold when opportunity is clear, but patient when it's not. Remember: "hold" is perfectly acceptable.

Respond with ONLY a JSON object in this exact format:
{{
  "operation": "buy_long" or "sell_short" or "close_long" or "close_short" or "hold",
  "symbol": "BTC" or "ETH" or "SOL" or "BNB" or "XRP" or "DOGE",
  "target_portion_of_balance": 0.15,
  "leverage": 3,
  "reason": "Your analysis considering short-term momentum, entry/exit timing, and position management"
}}

RULES - OPERATIONS:
- "buy_long": Open a LONG position (profit when price goes UP)
- "sell_short": Open a SHORT position (profit when price goes DOWN)
- "close_long": Close an existing LONG position (take profit or cut loss on long)
- "close_short": Close an existing SHORT position (take profit or cut loss on short)
- "hold": Wait for better opportunity (perfectly valid choice)

RULES - PARAMETERS:
- symbol: Which cryptocurrency to trade (you can hold multiple different coins simultaneously)
- target_portion_of_balance: % of available cash to use (0.0-1.0 for opening positions, 0.0-1.0 for closing)
  * For opening (buy_long/sell_short): portion of cash to use
  * For closing (close_long/close_short): portion of position to close (1.0 = close entire position)
- leverage: 1-50. Match leverage to your conviction level and market volatility
- reason: Explain your technical analysis, focusing on SHORT-TERM momentum and exit strategy

ADDITIONAL RULES:
- You can trade up to 100% of cash if conviction is very high
- Use higher leverage (20-50x) ONLY for exceptional opportunities with overwhelming technical confluence
- Consider all timeframes: rapid changes in 15m/1h suggest short-term opportunities, 4h/24h/7d show broader trends
- PRIORITY: Short-term trades, quick in and out, capture momentum
- When bearish, DON'T AVOID SHORTS - use "sell_short" to profit from falling prices
- Balance long and short positions based on market analysis"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {account.api_key}"
        }
        
        # Use OpenAI-compatible chat completions format
        payload = {
            "model": account.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.5,
            "max_tokens": 1000
        }
        
        # Construct API endpoint URL
        # Remove trailing slash from base_url if present
        base_url = account.base_url.rstrip('/')
        # Use /chat/completions endpoint (OpenAI-compatible)
        api_endpoint = f"{base_url}/chat/completions"
        
        # Log basic info (without full prompt)
        logger.info(f"Calling AI Model: {account.name} ({payload['model']})")
        logger.info(f"API Endpoint: {api_endpoint}")
        
        # Retry logic for rate limiting
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30,
                    verify=False  # Disable SSL verification for custom AI endpoints
                )
                
                if response.status_code == 200:
                    break  # Success, exit retry loop
                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                    logger.warning(f"AI API rate limited (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s...")
                    if attempt < max_retries - 1:  # Don't wait on the last attempt
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"AI API rate limited after {max_retries} attempts: {response.text}")
                        return None
                else:
                    logger.error(f"AI API returned status {response.status_code}: {response.text}")
                    return None
            except requests.RequestException as req_err:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"AI API request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s: {req_err}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"AI API request failed after {max_retries} attempts: {req_err}")
                    return None
        
        result = response.json()
        
        # Extract text from OpenAI-compatible response format
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            
            # Check if response was truncated due to length limit
            if finish_reason == "length":
                logger.warning(f"AI response was truncated due to token limit. Consider increasing max_tokens.")
                # Try to get content from reasoning field if available (some models put partial content there)
                text_content = message.get("reasoning", "") or message.get("content", "")
            else:
                text_content = message.get("content", "")
            
            if not text_content:
                logger.error(f"Empty content in AI response: {result}")
                return None
                
            # Try to extract JSON from the text
            # Sometimes AI might wrap JSON in markdown code blocks
            text_content = text_content.strip()
            if "```json" in text_content:
                text_content = text_content.split("```json")[1].split("```")[0].strip()
            elif "```" in text_content:
                text_content = text_content.split("```")[1].split("```")[0].strip()
            
            # Handle potential JSON parsing issues with escape sequences
            try:
                decision = json.loads(text_content)
            except json.JSONDecodeError as parse_err:
                # Try to fix common JSON issues
                logger.warning(f"Initial JSON parse failed: {parse_err}")
                logger.warning(f"Problematic content: {text_content[:200]}...")
                
                # Try to clean up the text content
                cleaned_content = text_content
                
                # Replace problematic characters that might break JSON
                cleaned_content = cleaned_content.replace('\n', ' ')
                cleaned_content = cleaned_content.replace('\r', ' ')
                cleaned_content = cleaned_content.replace('\t', ' ')
                
                # Handle unescaped quotes in strings by escaping them
                import re
                # Try a simpler approach to fix common JSON issues
                # Replace smart quotes and em-dashes with regular equivalents
                cleaned_content = cleaned_content.replace('"', '"').replace('"', '"')
                cleaned_content = cleaned_content.replace(''', "'").replace(''', "'")
                cleaned_content = cleaned_content.replace('–', '-').replace('—', '-')
                cleaned_content = cleaned_content.replace('‑', '-')  # Non-breaking hyphen
                
                # Try parsing again
                try:
                    decision = json.loads(cleaned_content)
                    logger.info("Successfully parsed JSON after cleanup")
                except json.JSONDecodeError:
                    # If still failing, try to extract just the essential parts
                    logger.error("JSON parsing failed even after cleanup, attempting manual extraction")
                    try:
                        # Extract operation, symbol, and target_portion manually
                        operation_match = re.search(r'"operation":\s*"([^"]+)"', text_content)
                        symbol_match = re.search(r'"symbol":\s*"([^"]+)"', text_content)
                        portion_match = re.search(r'"target_portion_of_balance":\s*([0-9.]+)', text_content)
                        reason_match = re.search(r'"reason":\s*"([^"]*)', text_content)
                        
                        if operation_match and symbol_match and portion_match:
                            decision = {
                                "operation": operation_match.group(1),
                                "symbol": symbol_match.group(1),
                                "target_portion_of_balance": float(portion_match.group(1)),
                                "reason": reason_match.group(1) if reason_match else "AI response parsing issue"
                            }
                            logger.info("Successfully extracted AI decision manually")
                        else:
                            raise json.JSONDecodeError("Could not extract required fields", text_content, 0)
                    except Exception:
                        raise parse_err  # Re-raise original error
            
            # Validate that decision is a dict with required structure
            if not isinstance(decision, dict):
                logger.error(f"AI response is not a dict: {type(decision)}")
                return None
            
            # Add the full prompt to the decision for logging
            decision['_prompt'] = prompt
            
            logger.info(f"AI decision for {account.name}: {decision.get('operation')} {decision.get('symbol', 'N/A')}")
            return decision
        
        logger.error(f"Unexpected AI response format: {result}")
        return None
        
    except requests.RequestException as err:
        logger.error(f"AI API request failed: {err}")
        return None
    except json.JSONDecodeError as err:
        logger.error(f"Failed to parse AI response as JSON: {err}")
        # Try to log the content that failed to parse
        try:
            if 'text_content' in locals():
                logger.error(f"Content that failed to parse: {text_content[:500]}")
        except:
            pass
        return None
    except Exception as err:
        logger.error(f"Unexpected error calling AI: {err}", exc_info=True)
        return None


def save_ai_decision(db: Session, account: Account, decision: Dict, portfolio: Dict, executed: bool = False, order_id: Optional[int] = None) -> None:
    """Save AI decision to the decision log"""
    try:
        operation = decision.get("operation", "").lower() if decision.get("operation") else ""
        symbol_raw = decision.get("symbol")
        symbol = symbol_raw.upper() if symbol_raw else None
        target_portion = float(decision.get("target_portion_of_balance", 0)) if decision.get("target_portion_of_balance") is not None else 0.0
        leverage = int(decision.get("leverage", 1))  # Extract leverage, default to 1x
        reason = decision.get("reason", "No reason provided")
        prompt = decision.get("_prompt", "")  # Extract full prompt from decision
        
        # 构建 AI 响应 JSON（不包括内部字段 _prompt）
        ai_response_json = {
            k: v for k, v in decision.items() 
            if not k.startswith('_')  # 排除内部字段
        }
        ai_response_json_str = json.dumps(ai_response_json, ensure_ascii=False)
        
        # Validate leverage range
        if leverage < 1:
            leverage = 1
        elif leverage > 50:
            leverage = 50
        
        # Calculate previous portion for the symbol
        prev_portion = 0.0
        if operation in ["sell", "hold"] and symbol:
            positions = portfolio.get("positions", {})
            if symbol in positions:
                symbol_value = positions[symbol]["current_value"]
                total_balance = portfolio["total_assets"]
                if total_balance > 0:
                    prev_portion = symbol_value / total_balance
        
        # Create decision log entry
        decision_log = AIDecisionLog(
            account_id=account.id,
            reason=reason,
            operation=operation,
            symbol=symbol if operation != "hold" else None,
            prev_portion=Decimal(str(prev_portion)),
            target_portion=Decimal(str(target_portion)),
            leverage=leverage,
            total_balance=Decimal(str(portfolio["total_assets"])),
            executed="true" if executed else "false",
            order_id=order_id,
            prompt=prompt,  # Save full prompt to database
            ai_response_json=ai_response_json_str  # Save AI response JSON
        )
        
        db.add(decision_log)
        db.commit()
        
        symbol_str = symbol if symbol else "N/A"
        logger.info(f"Saved AI decision log for account {account.name}: {operation} {symbol_str} "
                   f"leverage={leverage}x portion={target_portion:.2%} executed={executed}")
        logger.info(f"Prompt saved to database (length: {len(prompt)} chars)")
        
    except Exception as err:
        logger.error(f"Failed to save AI decision log: {err}")
        db.rollback()


def get_active_ai_accounts(db: Session) -> List[Account]:
    """Get all active AI accounts that are not using default API key"""
    accounts = db.query(Account).filter(
        Account.is_active == "true",
        Account.account_type == "AI"
    ).all()
    
    if not accounts:
        return []
    
    # Filter out default accounts
    valid_accounts = [acc for acc in accounts if not _is_default_api_key(acc.api_key)]
    
    if not valid_accounts:
        logger.debug("No valid AI accounts found (all using default keys)")
        return []
        
    return valid_accounts
