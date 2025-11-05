"""
Chart and Data API Routes
提供图表数据和分页数据查询的API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
from datetime import datetime, timedelta
from typing import List, Optional
from database.connection import get_db
from database.models import AIDecisionLog, Position, Order, Trade
from pydantic import BaseModel

router = APIRouter()


# ==================== Response Models ====================

class BalanceHistoryPoint(BaseModel):
    timestamp: str
    total_balance: float
    decision_id: int

    class Config:
        from_attributes = True


class BalanceHistoryResponse(BaseModel):
    data: List[BalanceHistoryPoint]
    has_more: bool
    next_end_time: Optional[str] = None


class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== Helper Functions ====================

def get_time_range_filter(time_range: str, end_time: Optional[datetime] = None):
    """
    根据时间范围返回过滤条件
    """
    now = end_time or datetime.now()
    
    if time_range == '24h':
        start = now - timedelta(hours=24)
    elif time_range == '1w':
        start = now - timedelta(days=7)
    elif time_range == '30d':
        start = now - timedelta(days=30)
    elif time_range == 'all':
        start = datetime(2000, 1, 1)  # 足够早的日期
    else:
        raise ValueError(f"Invalid time_range: {time_range}")
    
    return start


def aggregate_by_interval(data: List[AIDecisionLog], interval: str) -> List[BalanceHistoryPoint]:
    """
    根据时间周期聚合数据
    """
    if not data:
        return []
    
    if interval == '6m':
        # 6分钟：不聚合，直接返回
        return [
            BalanceHistoryPoint(
                timestamp=d.decision_time.isoformat(),
                total_balance=float(d.total_balance),
                decision_id=d.id
            )
            for d in data
        ]
    elif interval == '1h':
        # 1小时：取每小时的最后一个记录
        grouped = {}
        for d in data:
            hour_key = d.decision_time.replace(minute=0, second=0, microsecond=0)
            if hour_key not in grouped or d.decision_time > grouped[hour_key].decision_time:
                grouped[hour_key] = d
        
        return [
            BalanceHistoryPoint(
                timestamp=d.decision_time.isoformat(),
                total_balance=float(d.total_balance),
                decision_id=d.id
            )
            for d in sorted(grouped.values(), key=lambda x: x.decision_time)
        ]
    elif interval == '1d':
        # 1天：取每天的最后一个记录
        grouped = {}
        for d in data:
            day_key = d.decision_time.date()
            if day_key not in grouped or d.decision_time > grouped[day_key].decision_time:
                grouped[day_key] = d
        
        return [
            BalanceHistoryPoint(
                timestamp=d.decision_time.isoformat(),
                total_balance=float(d.total_balance),
                decision_id=d.id
            )
            for d in sorted(grouped.values(), key=lambda x: x.decision_time)
        ]
    else:
        raise ValueError(f"Invalid interval: {interval}")


# ==================== API Endpoints ====================

@router.get("/accounts/{account_id}/balance-history", response_model=BalanceHistoryResponse)
async def get_balance_history(
    account_id: int,
    time_range: str = Query(..., description="Time range: 24h, 1w, 30d, all"),
    interval: str = Query(..., description="Interval: 6m, 1h, 1d"),
    end_time: Optional[str] = Query(None, description="End time for pagination (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of points to return"),
    db: Session = Depends(get_db)
):
    """
    获取账户余额历史数据（用于图表）
    
    - time_range: 时间范围（24h, 1w, 30d, all）
    - interval: 时间周期（6m, 1h, 1d）
    - end_time: 用于分页加载历史数据（向左滑动）
    - limit: 返回的数据点数量
    """
    try:
        # 解析 end_time
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else datetime.now()
        
        # 获取时间范围
        start_dt = get_time_range_filter(time_range, end_dt)
        
        # 查询数据（按时间倒序）
        query = db.query(AIDecisionLog).filter(
            AIDecisionLog.account_id == account_id,
            AIDecisionLog.decision_time >= start_dt,
            AIDecisionLog.decision_time <= end_dt,
            AIDecisionLog.total_balance.isnot(None)
        ).order_by(desc(AIDecisionLog.decision_time)).limit(limit + 1)  # +1 to check if has_more
        
        results = query.all()
        
        # 检查是否还有更多数据
        has_more = len(results) > limit
        if has_more:
            results = results[:limit]
        
        # 反转顺序（从旧到新）
        results.reverse()
        
        # 根据 interval 聚合数据
        aggregated_data = aggregate_by_interval(results, interval)
        
        # 获取下一页的 end_time
        next_end_time = None
        if has_more and results:
            next_end_time = results[0].decision_time.isoformat()
        
        return BalanceHistoryResponse(
            data=aggregated_data,
            has_more=has_more,
            next_end_time=next_end_time
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch balance history: {str(e)}")


@router.get("/accounts/{account_id}/ai-decisions/paginated", response_model=PaginatedResponse)
async def get_ai_decisions_paginated(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    operation: Optional[str] = None,
    symbol: Optional[str] = None,
    executed: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    分页获取AI决策记录
    """
    try:
        # 构建查询
        query = db.query(AIDecisionLog).filter(AIDecisionLog.account_id == account_id)
        
        if operation:
            query = query.filter(AIDecisionLog.operation == operation)
        if symbol:
            query = query.filter(AIDecisionLog.symbol == symbol)
        if executed is not None:
            query = query.filter(AIDecisionLog.executed == executed)
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        offset = (page - 1) * page_size
        items = query.order_by(desc(AIDecisionLog.decision_time)).offset(offset).limit(page_size).all()
        
        # 转换为字典
        items_dict = [
            {
                "id": item.id,
                "account_id": item.account_id,
                "decision_time": item.decision_time.isoformat(),
                "reason": item.reason or "",
                "operation": item.operation or "",
                "symbol": item.symbol,
                "prev_portion": float(item.prev_portion) if item.prev_portion else 0.0,
                "target_portion": float(item.target_portion) if item.target_portion else 0.0,
                "total_balance": float(item.total_balance) if item.total_balance else 0.0,
                "executed": item.executed,
                "order_id": item.order_id
            }
            for item in items
        ]
        
        total_pages = (total + page_size - 1) // page_size
        
        return PaginatedResponse(
            items=items_dict,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI decisions: {str(e)}")


@router.get("/accounts/{account_id}/positions/paginated", response_model=PaginatedResponse)
async def get_positions_paginated(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    分页获取持仓记录
    """
    try:
        query = db.query(Position).filter(Position.account_id == account_id)
        
        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(desc(Position.id)).offset(offset).limit(page_size).all()
        
        items_dict = [
            {
                "id": item.id,
                "account_id": item.account_id,
                "symbol": item.symbol,
                "name": item.name,
                "market": item.market,
                "quantity": float(item.quantity),
                "available_quantity": float(item.available_quantity),
                "avg_cost": float(item.avg_cost),
                "last_price": float(item.last_price) if item.last_price else None,
                "market_value": float(item.market_value) if item.market_value else None
            }
            for item in items
        ]
        
        total_pages = (total + page_size - 1) // page_size
        
        return PaginatedResponse(
            items=items_dict,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {str(e)}")


@router.get("/accounts/{account_id}/orders/paginated", response_model=PaginatedResponse)
async def get_orders_paginated(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    分页获取订单记录
    """
    try:
        query = db.query(Order).filter(Order.account_id == account_id)
        
        if status:
            query = query.filter(Order.status == status)
        if symbol:
            query = query.filter(Order.symbol.like(f"%{symbol}%"))
        
        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(desc(Order.created_at)).offset(offset).limit(page_size).all()
        
        items_dict = [
            {
                "id": item.id,
                "order_no": item.order_no,
                "symbol": item.symbol,
                "name": item.name,
                "market": item.market,
                "side": item.side,
                "order_type": item.order_type,
                "price": float(item.price) if item.price else None,
                "quantity": float(item.quantity),
                "filled_quantity": float(item.filled_quantity),
                "status": item.status,
                "created_at": item.created_at.isoformat()
            }
            for item in items
        ]
        
        total_pages = (total + page_size - 1) // page_size
        
        return PaginatedResponse(
            items=items_dict,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch orders: {str(e)}")


@router.get("/accounts/{account_id}/trades/paginated", response_model=PaginatedResponse)
async def get_trades_paginated(
    account_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    symbol: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    分页获取成交记录
    """
    try:
        query = db.query(Trade).filter(Trade.account_id == account_id)
        
        if symbol:
            query = query.filter(Trade.symbol.like(f"%{symbol}%"))
        
        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(desc(Trade.trade_time)).offset(offset).limit(page_size).all()
        
        items_dict = [
            {
                "id": item.id,
                "order_id": item.order_id,
                "account_id": item.account_id,
                "symbol": item.symbol,
                "name": item.name,
                "market": item.market,
                "side": item.side,
                "price": float(item.price),
                "quantity": float(item.quantity),
                "commission": float(item.commission),
                "trade_time": item.trade_time.isoformat()
            }
            for item in items
        ]
        
        total_pages = (total + page_size - 1) // page_size
        
        return PaginatedResponse(
            items=items_dict,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trades: {str(e)}")
