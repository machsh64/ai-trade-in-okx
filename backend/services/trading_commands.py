"""
Trading Commands Service - Handles order execution and trading logic
使用OKX真实交易API执行订单
"""
import logging
import random
from decimal import Decimal
from typing import Dict, Optional, Tuple, List
from datetime import datetime

from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Position, Account, Order, Trade
from services.asset_calculator import calc_positions_value
from services.market_data import get_last_price
from services.okx_trading_executor import create_okx_order  # 使用OKX真实交易
from services.ai_decision_service import (
    call_ai_for_decision, 
    save_ai_decision, 
    get_active_ai_accounts, 
    _get_portfolio_data,
    SUPPORTED_SYMBOLS
)


logger = logging.getLogger(__name__)

AI_TRADING_SYMBOLS: List[str] = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]


async def _notify_account_update(account_id: int):
    """
    通知WebSocket客户端账户数据已更新
    在AI交易完成后触发快照更新
    """
    try:
        from api.ws import manager, _send_snapshot
        db = SessionLocal()
        try:
            await _send_snapshot(db, account_id)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to send WebSocket update for account {account_id}: {e}")


def _save_okx_order_to_db(
    db: Session,
    account: Account,
    okx_result: Dict,
    symbol: str,
    name: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    price: Optional[float] = None
) -> Optional[Tuple[Order, Trade]]:
    """
    保存OKX订单到本地数据库，以便前端显示
    
    Args:
        db: 数据库会话
        account: 账户对象
        okx_result: OKX API返回的结果
        symbol: 交易对符号 (e.g., "BTC-USDT-SWAP")
        name: 币种名称 (e.g., "Bitcoin")
        side: 'buy' or 'sell'
        quantity: 数量
        order_type: 'market' or 'limit'
        price: 价格（如果是限价单）
    
    Returns:
        (Order, Trade) 元组，如果保存失败则返回None
    """
    try:
        # 生成唯一订单号
        import uuid
        order_no = f"OKX-{uuid.uuid4().hex[:16].upper()}"
        
        # 从OKX结果中提取信息
        okx_order_id = okx_result.get('order_id')
        okx_price = okx_result.get('price')  # OKX返回的实际成交价
        
        # 如果OKX返回了价格，使用OKX的价格；否则查询市场价
        if okx_price:
            execution_price = float(okx_price)
        else:
            # 查询当前市场价（去掉-USDT-SWAP后缀）
            base_symbol = symbol.split('-')[0]
            try:
                execution_price = get_last_price(base_symbol, "CRYPTO")
            except:
                # 如果价格查询失败，使用传入的价格或默认值
                execution_price = price if price else 0.0
        
        # 创建订单记录
        order = Order(
            account_id=account.id,
            order_no=order_no,
            symbol=symbol,
            name=name,
            market="CRYPTO",
            side=side.upper(),
            order_type=order_type.upper(),
            price=Decimal(str(execution_price)) if execution_price else None,
            quantity=Decimal(str(quantity)),
            filled_quantity=Decimal(str(quantity)),  # 市价单立即完全成交
            status="FILLED",  # OKX成功返回表示已成交
            created_at=datetime.now()
        )
        db.add(order)
        db.flush()  # 刷新以获取order.id
        
        # 创建成交记录
        commission = Decimal(str(quantity * execution_price * 0.0005))  # 假设手续费率0.05%
        trade = Trade(
            order_id=order.id,
            account_id=account.id,
            symbol=symbol,
            name=name,
            market="CRYPTO",
            side=side.upper(),
            price=Decimal(str(execution_price)),
            quantity=Decimal(str(quantity)),
            commission=commission,
            trade_time=datetime.now()
        )
        db.add(trade)
        db.commit()
        
        logger.info(
            f"✅ Saved OKX order to database: order_id={order.id}, "
            f"trade_id={trade.id}, okx_order_id={okx_order_id}"
        )
        
        return (order, trade)
        
    except Exception as e:
        logger.error(f"Failed to save OKX order to database: {e}", exc_info=True)
        db.rollback()
        return None


def _get_market_prices(symbols: List[str]) -> Dict[str, float]:
    """Get latest prices for given symbols"""
    prices = {}
    for symbol in symbols:
        try:
            price = float(get_last_price(symbol, "CRYPTO"))
            if price > 0:
                prices[symbol] = price
        except Exception as err:
            logger.warning(f"Failed to get price for {symbol}: {err}")
    return prices


def _select_side(db: Session, account: Account, symbol: str, max_value: float) -> Optional[Tuple[str, int]]:
    """Select random trading side and quantity for legacy random trading"""
    market = "CRYPTO"
    try:
        price = float(get_last_price(symbol, market))
    except Exception as err:
        logger.warning("Cannot get price for %s: %s", symbol, err)
        return None

    if price <= 0:
        logger.debug("%s returned non-positive price %s", symbol, price)
        return None

    max_quantity_by_value = int(Decimal(str(max_value)) // Decimal(str(price)))
    position = (
        db.query(Position)
        .filter(Position.account_id == account.id, Position.symbol == symbol, Position.market == market)
        .first()
    )
    available_quantity = int(position.available_quantity) if position else 0

    choices = []

    if float(account.current_cash) >= price and max_quantity_by_value >= 1:
        choices.append(("BUY", max_quantity_by_value))

    if available_quantity > 0:
        max_sell_quantity = min(available_quantity, max_quantity_by_value if max_quantity_by_value >= 1 else available_quantity)
        if max_sell_quantity >= 1:
            choices.append(("SELL", max_sell_quantity))

    if not choices:
        return None

    side, max_qty = random.choice(choices)
    quantity = random.randint(1, max_qty)
    return side, quantity


def place_ai_driven_crypto_order(max_ratio: float = 0.2, manual_decision: dict = None) -> None:
    """
    Place crypto order based on AI model decision for all active accounts
    
    参数：
        max_ratio: 最大仓位比例（默认 0.2 = 20%）
        manual_decision: 手动测试决策数据（可选）
                        如果提供此参数，则使用手动决策而不调用AI接口
                        仅用于测试脚本，不影响正常AI定时任务
    """
    db = SessionLocal()
    try:
        accounts = get_active_ai_accounts(db)
        if not accounts:
            logger.debug("No available accounts, skipping AI trading")
            return

        # Get latest market prices once for all accounts
        prices = _get_market_prices(AI_TRADING_SYMBOLS)
        if not prices:
            logger.warning("Failed to fetch market prices, skipping AI trading")
            return

        # Iterate through all active accounts
        for account in accounts:
            try:
                if manual_decision:
                    logger.info(f"🧪 [TEST MODE] Processing manual test for account: {account.name}")
                else:
                    logger.info(f"Processing AI trading for account: {account.name}")
                
                # Get portfolio data for this account
                portfolio = _get_portfolio_data(db, account)
                
                if portfolio['total_assets'] <= 0:
                    logger.debug(f"Account {account.name} has non-positive total assets, skipping")
                    continue

                # 如果提供了 manual_decision 参数，使用手动测试数据（仅测试脚本使用）
                # 否则调用 AI API 获取决策（正常定时任务流程）
                if manual_decision:
                    decision = manual_decision
                    logger.info(f"📋 [TEST MODE] Using manual decision: {decision}")
                else:
                    # Call AI for trading decision (传入 db 参数以获取历史记录)
                    decision = call_ai_for_decision(account, portfolio, prices, db=db)
                    if not decision or not isinstance(decision, dict):
                        logger.warning(f"Failed to get AI decision for {account.name}, skipping")
                        continue

                operation = decision.get("operation", "").lower() if decision.get("operation") else ""
                symbol = decision.get("symbol", "").upper() if decision.get("symbol") else ""
                target_portion = float(decision.get("target_portion_of_balance", 0)) if decision.get("target_portion_of_balance") is not None else 0
                reason = decision.get("reason", "No reason provided")

                logger.info(f"AI decision for {account.name}: {operation} {symbol} (portion: {target_portion:.2%}) - {reason}")

                # Validate decision
                if operation not in ["buy_long", "sell_short", "close_long", "close_short", "hold"]:
                    logger.warning(f"Invalid operation '{operation}' from AI for {account.name}, skipping")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue
                
                if operation == "hold":
                    logger.info(f"AI decided to HOLD for {account.name}")
                    save_ai_decision(db, account, decision, portfolio, executed=True)
                    continue

                if symbol not in SUPPORTED_SYMBOLS:
                    logger.warning(f"Invalid symbol '{symbol}' from AI for {account.name}, skipping")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                if target_portion <= 0 or target_portion > 1:
                    logger.warning(f"Invalid target_portion {target_portion} from AI for {account.name}, skipping")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue

                # 获取杠杆倍数
                leverage = int(decision.get("leverage", 3))
                if leverage < 1:
                    leverage = 1
                elif leverage > 125:
                    leverage = 125
                
                # 格式化symbol
                name = SUPPORTED_SYMBOLS[symbol]
                okx_symbol = f"{symbol}-USDT-SWAP"  # OKX永续合约格式
                ccxt_symbol = f"{symbol}/USDT:USDT"  # CCXT格式
                
                # 从OKX获取余额信息和当前持仓（传入account使用其配置）
                from services.okx_market_data import fetch_balance_okx, fetch_positions_okx
                
                # fetch_balance_okx 返回 CCXT 原始格式，不是 {success: true, balances: ...}
                try:
                    balance_result = fetch_balance_okx(account=account)
                    logger.info(f"[DEBUG] Fetched balance from OKX")
                    
                    # CCXT格式：{'USDT': {'free': 100, 'used': 10, 'total': 110}, ...}
                    usdt_balance = balance_result.get('USDT', {})
                    available_balance = float(usdt_balance.get('free', 0))
                    
                    logger.info(f"[DEBUG] Available USDT balance: ${available_balance:.2f}")
                except Exception as e:
                    logger.error(f"Failed to fetch OKX balance for {account.name}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue
                
                # 获取当前持仓（fetch_positions_okx返回的是列表，不是字典）
                # 注意：OKX 双向持仓模式下，同一个 symbol 可能有 long 和 short 两个持仓
                try:
                    positions_list = fetch_positions_okx(account=account)
                    logger.info(f"[DEBUG] Fetched {len(positions_list)} positions from OKX")
                    
                    # 对于双向持仓，需要根据操作类型匹配对应方向的持仓
                    current_position = None
                    target_pos_side = None
                    
                    # 预判断：根据操作类型确定需要的持仓方向
                    if operation in ["close_long"]:
                        target_pos_side = "long"
                    elif operation in ["close_short"]:
                        target_pos_side = "short"
                    
                    for pos in positions_list:
                        pos_symbol = pos.get('symbol')
                        pos_contracts = pos.get('contracts', 0)
                        pos_side_field = pos.get('side') or pos.get('posSide')
                        
                        logger.info(f"[DEBUG] Position: {pos_symbol}, contracts={pos_contracts}, side={pos.get('side')}, posSide={pos.get('posSide')}")
                        
                        # 匹配 symbol 和持仓方向（如果是 close 操作）
                        if pos_symbol == ccxt_symbol:
                            if target_pos_side:
                                # close 操作：需要匹配持仓方向
                                if pos_side_field == target_pos_side and abs(float(pos_contracts)) > 0:
                                    current_position = pos
                                    logger.info(f"[DEBUG] Found matching {target_pos_side} position for {ccxt_symbol}")
                                    break
                            else:
                                # open 操作：不需要匹配方向，找到任意持仓即可
                                current_position = pos
                                logger.info(f"[DEBUG] Found matching position for {ccxt_symbol}")
                                break
                    
                    if not current_position and target_pos_side:
                        logger.info(f"[DEBUG] No matching {target_pos_side} position found for {ccxt_symbol}")
                    elif not current_position:
                        logger.info(f"[DEBUG] No matching position found for {ccxt_symbol}")
                except Exception as e:
                    logger.error(f"Failed to fetch positions from OKX: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    current_position = None
                
                # 确定交易参数
                side = None  # buy或sell
                pos_side = None  # long或short
                quantity = None
                
                # 获取当前价格（用于计算开仓数量）
                from services.okx_market_data import fetch_ticker_okx, get_market_precision_okx, _get_client
                try:
                    ticker = fetch_ticker_okx(ccxt_symbol, account=account)
                    current_price = float(ticker.get('last', 0))
                    if current_price <= 0:
                        logger.error(f"Invalid price for {symbol}, skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    logger.info(f"[DEBUG] Current price for {symbol}: ${current_price:.2f}")
                    
                    # 获取市场精度信息和合约大小
                    precision_info = get_market_precision_okx(ccxt_symbol, account=account)
                    amount_precision = precision_info.get('amount', 1)
                    min_amount = precision_info.get('min_amount', 1)
                    max_amount = precision_info.get('max_amount', None)  # 最大数量限制
                    max_cost = precision_info.get('max_cost', None)  # 最大金额限制
                    
                    # 获取合约大小（contractSize）
                    # 对于 BTC-USDT-SWAP：1张合约 = 0.01 BTC
                    # 对于 ETH-USDT-SWAP：1张合约 = 0.01 ETH
                    client = _get_client(account=account)
                    if not client.public_exchange.markets:
                        client.public_exchange.load_markets()
                    market = client.public_exchange.markets.get(ccxt_symbol)
                    contract_size = market.get('contractSize', 1) if market else 1  # 默认为1（现货）
                    
                    logger.info(f"[DEBUG] Market info for {symbol}: amount_precision={amount_precision}, min_amount={min_amount}, max_amount={max_amount}, max_cost={max_cost}, contractSize={contract_size}")
                    
                except Exception as e:
                    logger.error(f"Failed to fetch price/precision for {symbol}: {e}")
                    save_ai_decision(db, account, decision, portfolio, executed=False)
                    continue
                
                if operation == "buy_long":
                    # 开多仓
                    side = "buy"
                    pos_side = "long"
                    
                    if available_balance <= 0:
                        logger.info(f"No funds available to BUY_LONG {symbol}, skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    # 计算开仓数量：(资金 * 比例 * 杠杆) / 当前价格
                    order_value_usdt = available_balance * target_portion * leverage
                    quantity_in_base = order_value_usdt / current_price  # 币的数量（如 BTC 数量）
                    
                    # 对于永续合约，CCXT的amount参数是合约张数，不是币的数量
                    # 需要将币的数量转换为合约张数：quantity = 币数量 / contractSize
                    # 例如：25.94 BTC / 0.01 (contractSize) = 2594 张合约
                    quantity_in_contracts = quantity_in_base / contract_size if contract_size > 0 else quantity_in_base
                    
                    logger.info(f"[DEBUG] Calculated quantity: {quantity_in_base:.4f} {symbol} = {quantity_in_contracts:.2f} contracts (contractSize={contract_size})")
                    
                    # 使用合约张数进行后续计算
                    quantity = quantity_in_contracts
                    
                    # 使用OKX返回的精度信息进行舍入
                    # amount_precision 是精度值，如 0.01（两位小数）、0.001（三位小数）、1（整数）
                    if amount_precision >= 1:
                        # 精度>=1表示只能是整数（如DOGE，amount_precision=1）
                        quantity = int(quantity)
                    else:
                        # 精度<1表示小数（如BTC的0.01, 0.001等）
                        # 将精度值转换为小数位数：0.01 -> 2, 0.001 -> 3
                        import math
                        decimal_places = -int(math.log10(amount_precision))
                        quantity = round(quantity, decimal_places)
                    
                    # 确保不低于最小数量
                    if quantity < min_amount:
                        logger.warning(f"Calculated quantity {quantity} contracts below min {min_amount}, adjusting")
                        quantity = min_amount
                    
                    # 检查是否超过最大数量限制
                    if max_amount and quantity > max_amount:
                        logger.warning(f"Calculated quantity {quantity} contracts exceeds max {max_amount}, capping to maximum")
                        quantity = max_amount
                    
                    # 检查是否超过最大金额限制
                    if max_cost:
                        # max_cost 是 USDT 金额限制
                        # 先转换为币的数量，再转换为合约张数
                        max_quantity_in_base = max_cost / current_price
                        max_quantity_in_contracts = max_quantity_in_base / contract_size if contract_size > 0 else max_quantity_in_base
                        if quantity > max_quantity_in_contracts:
                            logger.warning(f"Calculated quantity {quantity} contracts exceeds max cost limit (max_cost=${max_cost}), capping to {max_quantity_in_contracts}")
                            quantity = max_quantity_in_contracts
                            # 重新应用精度
                            if amount_precision >= 1:
                                quantity = int(quantity)
                            else:
                                import math
                                decimal_places = -int(math.log10(amount_precision))
                                quantity = round(quantity, decimal_places)
                    
                    # 计算实际币数量（用于日志）
                    actual_base_quantity = quantity * contract_size
                    actual_cost = actual_base_quantity * current_price
                    logger.info(f"[DEBUG] Final buy_long: {quantity} contracts = {actual_base_quantity:.4f} {symbol} (value=${actual_cost:.2f})")
                    
                    if quantity <= 0:
                        logger.info(f"Calculated quantity too small for {symbol}, skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                
                elif operation == "sell_short":
                    # 开空仓
                    side = "sell"
                    pos_side = "short"
                    
                    if available_balance <= 0:
                        logger.info(f"No funds available to SELL_SHORT {symbol}, skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    # 计算开仓数量：(资金 * 比例 * 杠杆) / 当前价格
                    order_value_usdt = available_balance * target_portion * leverage
                    quantity_in_base = order_value_usdt / current_price  # 币的数量（如 BTC 数量）
                    
                    # 对于永续合约，CCXT的amount参数是合约张数，不是币的数量
                    # 需要将币的数量转换为合约张数：quantity = 币数量 / contractSize
                    # 例如：25.94 BTC / 0.01 (contractSize) = 2594 张合约
                    quantity_in_contracts = quantity_in_base / contract_size if contract_size > 0 else quantity_in_base
                    
                    logger.info(f"[DEBUG] Calculated quantity: {quantity_in_base:.4f} {symbol} = {quantity_in_contracts:.2f} contracts (contractSize={contract_size})")
                    
                    # 使用合约张数进行后续计算
                    quantity = quantity_in_contracts
                    
                    # 使用OKX返回的精度信息进行舍入
                    # amount_precision 是精度值，如 0.01（两位小数）、0.001（三位小数）、1（整数）
                    if amount_precision >= 1:
                        # 精度>=1表示只能是整数（如DOGE，amount_precision=1）
                        quantity = int(quantity)
                    else:
                        # 精度<1表示小数（如BTC的0.01, 0.001等）
                        # 将精度值转换为小数位数：0.01 -> 2, 0.001 -> 3
                        import math
                        decimal_places = -int(math.log10(amount_precision))
                        quantity = round(quantity, decimal_places)
                    
                    # 确保不低于最小数量
                    if quantity < min_amount:
                        logger.warning(f"Calculated quantity {quantity} contracts below min {min_amount}, adjusting")
                        quantity = min_amount
                    
                    # 检查是否超过最大数量限制
                    if max_amount and quantity > max_amount:
                        logger.warning(f"Calculated quantity {quantity} contracts exceeds max {max_amount}, capping to maximum")
                        quantity = max_amount
                    
                    # 检查是否超过最大金额限制
                    if max_cost:
                        # max_cost 是 USDT 金额限制
                        # 先转换为币的数量，再转换为合约张数
                        max_quantity_in_base = max_cost / current_price
                        max_quantity_in_contracts = max_quantity_in_base / contract_size if contract_size > 0 else max_quantity_in_base
                        if quantity > max_quantity_in_contracts:
                            logger.warning(f"Calculated quantity {quantity} contracts exceeds max cost limit (max_cost=${max_cost}), capping to {max_quantity_in_contracts}")
                            quantity = max_quantity_in_contracts
                            # 重新应用精度
                            if amount_precision >= 1:
                                quantity = int(quantity)
                            else:
                                import math
                                decimal_places = -int(math.log10(amount_precision))
                                quantity = round(quantity, decimal_places)
                    
                    # 计算实际币数量（用于日志）
                    actual_base_quantity = quantity * contract_size
                    actual_cost = actual_base_quantity * current_price
                    logger.info(f"[DEBUG] Final sell_short: {quantity} contracts = {actual_base_quantity:.4f} {symbol} (value=${actual_cost:.2f})")
                    
                    if quantity <= 0:
                        logger.info(f"Calculated quantity too small for {symbol}, skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                
                elif operation == "close_long":
                    # 平多仓
                    side = "sell"
                    pos_side = "long"
                    
                    logger.info(f"[DEBUG] close_long operation for {symbol}:")
                    logger.info(f"[DEBUG]   current_position: {current_position is not None}")
                    
                    if not current_position:
                        logger.info(f"[FAIL] close_long: No position found for {symbol}, skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    # 检查持仓（CCXT可能返回'side'或'posSide'字段）
                    side_field = current_position.get('side')
                    pos_side_field = current_position.get('posSide')
                    position_side = side_field or pos_side_field
                    
                    logger.info(f"[DEBUG]   side field: {side_field}")
                    logger.info(f"[DEBUG]   posSide field: {pos_side_field}")
                    logger.info(f"[DEBUG]   detected position_side: {position_side}")
                    
                    if position_side != 'long':
                        logger.info(f"[FAIL] close_long: Position is not long (position_side={position_side}), skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    contracts = float(current_position.get('contracts', 0))
                    logger.info(f"[DEBUG]   contracts: {contracts}")
                    
                    if contracts <= 0:
                        logger.info(f"[FAIL] close_long: No contracts in long position for {symbol} (contracts={contracts}), skipping")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    quantity = max(1, int(contracts * target_portion))
                    logger.info(f"[DEBUG]   calculated quantity: {quantity} (target_portion={target_portion})")
                
                elif operation == "close_short":
                    # 平空仓
                    side = "buy"
                    pos_side = "short"
                    
                    logger.info(f"[DEBUG] ===== CLOSE_SHORT OPERATION START =====")
                    logger.info(f"[DEBUG] Account: {account.name} (ID: {account.id})")
                    logger.info(f"[DEBUG] Symbol: {symbol}, OKX Symbol: {okx_symbol}")
                    logger.info(f"[DEBUG] Target Portion: {target_portion}")
                    logger.info(f"[DEBUG] Current Position (should be SHORT): {current_position}")
                    
                    if not current_position:
                        logger.error(f"[FAIL] close_short: No SHORT position found for {symbol}. Account: {account.name}")
                        logger.error(f"[FAIL] Note: In dual-position mode, you may have a LONG position but no SHORT position for this symbol.")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    # 检查持仓（CCXT可能返回'side'或'posSide'字段）
                    side_field = current_position.get('side')
                    pos_side_field = current_position.get('posSide')
                    position_side = side_field or pos_side_field
                    
                    logger.info(f"[DEBUG]   side field: {side_field}")
                    logger.info(f"[DEBUG]   posSide field: {pos_side_field}")
                    logger.info(f"[DEBUG]   detected position_side: {position_side}")
                    
                    if position_side != 'short':
                        logger.error(f"[FAIL] close_short: Position is not short (position_side={position_side}). Account: {account.name}, Symbol: {symbol}")
                        logger.error(f"[FAIL] This should not happen after position matching. Check dual-position mode logic.")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    contracts = float(current_position.get('contracts', 0))
                    logger.info(f"[DEBUG]   contracts: {contracts}")
                    
                    if contracts <= 0:
                        logger.error(f"[FAIL] close_short: No contracts in short position for {symbol} (contracts={contracts}). Account: {account.name}")
                        save_ai_decision(db, account, decision, portfolio, executed=False)
                        continue
                    
                    quantity = max(1, int(contracts * target_portion))
                    logger.info(f"[DEBUG]   calculated quantity: {quantity} (target_portion={target_portion})")
                    logger.info(f"[DEBUG] Ready to execute: side={side}, pos_side={pos_side}, quantity={quantity}")
                
                else:
                    continue

                logger.info(f"[EXECUTE] Executing OKX order: {operation} ({side}/{pos_side}) {quantity} {okx_symbol} with {leverage}x leverage")
                logger.info(f"[EXECUTE] Account: {account.name} (ID: {account.id})")
                
                # 对于平仓操作，在下单前再次确认当前持仓状态（防止重复下单导致错误）
                is_close_operation = operation in ["close_long", "close_short"]
                if is_close_operation:
                    from services.okx_market_data import fetch_positions_okx
                    logger.info(f"[PRE-EXECUTE] Fetching latest positions before placing order...")
                    try:
                        latest_positions = fetch_positions_okx(symbol=ccxt_symbol, account=account)
                        logger.info(f"[PRE-EXECUTE] Latest positions for {ccxt_symbol}: {latest_positions}")
                        
                        # 筛选出目标方向的持仓
                        target_positions = [p for p in latest_positions if p.get('symbol') == ccxt_symbol and (p.get('side') == pos_side or p.get('posSide') == pos_side)]
                        logger.info(f"[PRE-EXECUTE] Target {pos_side} positions: {target_positions}")
                        
                        if not target_positions or all(float(p.get('contracts', 0)) <= 0 for p in target_positions):
                            logger.error(f"[FAIL] No {pos_side} position found for {ccxt_symbol} before execution. Position may have been closed already.")
                            save_ai_decision(db, account, decision, portfolio, executed=False)
                            continue
                    except Exception as e:
                        logger.warning(f"[PRE-EXECUTE] Failed to fetch latest positions: {e}. Continuing with order...")
                
                # 只在开仓操作时设置杠杆（平仓不需要设置杠杆）
                if not is_close_operation:
                    from services.okx_market_data import set_leverage_okx
                    logger.info(f"[LEVERAGE] Setting leverage {leverage}x for {symbol}...")
                    leverage_result = set_leverage_okx(
                        symbol=ccxt_symbol,
                        leverage=leverage,
                        margin_mode='cross',  # 使用全仓模式
                        account=account  # 传入账户对象
                    )
                    
                    if not leverage_result.get('success'):
                        logger.warning(f"[LEVERAGE] Failed to set leverage for {symbol}: {leverage_result.get('error')}")
                        # 继续执行订单，即使杠杆设置失败
                    else:
                        logger.info(f"[LEVERAGE] Successfully set {leverage}x leverage for {symbol}")
                else:
                    logger.info(f"[LEVERAGE] Skipping leverage setting for close operation")
                
                # 调用OKX API下单，传入account和posSide参数
                # 对于平仓操作，添加 reduceOnly=True 确保只平仓不开新仓
                is_close_operation = operation in ["close_long", "close_short"]
                order_params = {
                    'posSide': pos_side,  # 'long' 或 'short'
                    'tdMode': 'cross'  # 全仓模式
                }
                if is_close_operation:
                    order_params['reduceOnly'] = True  # 只平仓，不开新仓
                
                logger.info(f"[OKX] Calling create_okx_order with params: symbol={okx_symbol}, side={side.lower()}, amount={quantity}, posSide={pos_side}, reduceOnly={is_close_operation}")
                result = create_okx_order(
                    symbol=okx_symbol,
                    side=side.lower(),
                    amount=quantity,
                    order_type="market",  # AI交易使用市价单
                    price=None,
                    params=order_params,
                    account=account  # 传入account使用其OKX配置
                )
                
                logger.info(f"[OKX] create_okx_order result: success={result.get('success')}, error={result.get('error')}, order_id={result.get('order_id')}")
                
                if result.get('success'):
                    logger.info(
                        f"✅ [SUCCESS] OKX AI order executed: {side} {quantity} {symbol} @ {leverage}x leverage "
                        f"order_id={result.get('order_id')} reason='{reason}'"
                    )
                    
                    # 保存订单到本地数据库，以便前端显示
                    saved = _save_okx_order_to_db(
                        db=db,
                        account=account,
                        okx_result=result,
                        symbol=okx_symbol,
                        name=name,
                        side=side.lower(),
                        quantity=quantity,
                        order_type="market"
                    )
                    
                    # 保存AI决策记录（executed=True）
                    order_id = saved[0].id if saved else None
                    save_ai_decision(db, account, decision, portfolio, executed=True, order_id=order_id)
                    
                    # 触发WebSocket通知，让前端实时更新
                    if saved:
                        try:
                            from api.ws import manager
                            import asyncio
                            # 检查是否有运行的事件循环
                            try:
                                loop = asyncio.get_running_loop()
                                # 在运行的事件循环中创建任务
                                asyncio.create_task(_notify_account_update(account.id))
                            except RuntimeError:
                                # 没有运行的事件循环，使用 run_coroutine_threadsafe
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        asyncio.run_coroutine_threadsafe(_notify_account_update(account.id), loop)
                                    else:
                                        # 事件循环未运行，跳过 WebSocket 通知
                                        logger.debug("Event loop not running, skipping WebSocket notification")
                                except Exception:
                                    logger.debug("No event loop available, skipping WebSocket notification")
                        except Exception as notify_err:
                            logger.debug(f"WebSocket notification skipped: {notify_err}")
                    
                else:
                    logger.error(
                        f"❌ [FAILED] OKX AI order failed: {side} {quantity} {symbol} "
                        f"error={result.get('error')} | Full result: {result}"
                    )
                    logger.error(f"[FAILED] Account: {account.name} (ID: {account.id}), Operation: {operation}")
                    # 保存失败的决策
                    save_ai_decision(db, account, decision, portfolio, executed=False, order_id=None)

            except Exception as account_err:
                logger.error(f"❌ [EXCEPTION] AI-driven order placement failed for account {account.name}: {account_err}", exc_info=True)
                # Continue with next account even if one fails

    except Exception as err:
        logger.error(f"❌ [EXCEPTION] AI-driven order placement failed: {err}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def place_random_crypto_order(max_ratio: float = 0.2) -> None:
    """
    Legacy random order placement - DEPRECATED
    已废弃：现在所有交易都通过OKX真实API执行，不再支持随机模拟交易
    """
    logger.warning("place_random_crypto_order is deprecated. All trading now uses OKX API via AI decisions.")
    pass  # 不再执行随机模拟交易


AUTO_TRADE_JOB_ID = "auto_crypto_trade"
AI_TRADE_JOB_ID = "ai_crypto_trade"