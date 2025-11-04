"""
手动触发AI交易测试脚本 - 模拟AI返回数据真实下单
用于测试交易流程，使用手动构造的决策数据（不调用真实AI）

使用方法：
1. 修改下面 TEST_DECISION 字典中的参数（操作类型、标的、仓位、杠杆等）
2. 运行本脚本: python test_ai_payload.py
3. 订单将发送到 OKX 真实环境/沙盒
4. 在 OKX 交易平台查看订单执行效果

测试参数配置说明：
- operation: 操作类型
  * "buy_long" - 开多仓
  * "sell_short" - 开空仓
  * "close_position" - 平仓
  * "hold" - 持有不操作
- symbol: 交易标的（BTC, ETH, SOL, BNB, XRP, DOGE 等）
- target_portion_of_balance: 仓位比例（0.0-1.0，例如 0.25 表示 25%）
- leverage: 杠杆倍数（1-125，根据交易所限制）
- reason: 交易原因说明（可选）
"""
import sys
import os
import logging

# 设置Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志，确保能看到所有输出
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到控制台
        logging.FileHandler('test_ai_trade.log', encoding='utf-8')  # 同时保存到文件
    ]
)

from services.trading_commands import place_ai_driven_crypto_order

# ==================== 测试参数配置区域 ====================
# 在这里修改测试参数，不会影响正常的AI交易流程
TEST_DECISION = {
    "operation": "buy_long",              # 操作类型: buy_long, sell_short, close_position, hold
    "symbol": "SOL",                      # 交易标的: BTC, ETH, SOL, BNB, XRP, DOGE
    "target_portion_of_balance": 0.25,    # 仓位比例: 0.25 = 25%
    "leverage": 8,                        # 杠杆倍数: 1-125
    "reason": "Manual test - 手动测试 25% 仓位 8倍杠杆开多 SOL"  # 交易原因
}
# ========================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🤖 手动测试 - 模拟AI决策真实下单")
    print("=" * 80)
    print("\n📋 当前测试配置:")
    print(f"  - 操作类型: {TEST_DECISION['operation']}")
    print(f"  - 交易标的: {TEST_DECISION['symbol']}")
    print(f"  - 仓位比例: {TEST_DECISION['target_portion_of_balance']*100:.0f}%")
    print(f"  - 杠杆倍数: {TEST_DECISION['leverage']}x")
    print(f"  - 交易原因: {TEST_DECISION['reason']}")
    print("  - 订单类型: 市价单")
    print("\n⚠️  注意:")
    print("  1. 此脚本使用上面配置的测试参数，不会调用AI接口")
    print("  2. 确保数据库中有活跃的 AI 账户（is_active=true, account_type='AI'）")
    print("  3. 确保账户配置了正确的 OKX API 密钥")
    print("  4. 此脚本会发送真实订单到 OKX（根据 okx_sandbox 配置）")
    print("\n" + "=" * 80)
    print("开始执行交易流程...\n")
    
    try:
        # 传递测试决策数据给交易函数
        place_ai_driven_crypto_order(manual_decision=TEST_DECISION)
        
        print("\n" + "=" * 80)
        print("✅ 交易流程执行完成!")
        print("=" * 80)
        print("\n📊 查看结果:")
        print("  1. 查看上面的日志输出，包含详细的执行过程")
        print("  2. 查看 test_ai_trade.log 文件获取完整日志")
        print("  3. 登录 OKX 交易平台查看订单状态")
        print("  4. 检查数据库 ai_decision_logs 表查看决策记录")
        print("  5. 检查数据库 orders 和 trades 表查看订单记录")
        print("\n")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 测试失败!")
        print("=" * 80)
        print(f"\n错误信息: {e}\n")
        print("详细错误堆栈:")
        import traceback
        traceback.print_exc()
        print("\n💡 排查建议:")
        print("  1. 检查数据库连接是否正常")
        print("  2. 确认有活跃的 AI 账户")
        print("  3. 验证 OKX API 配置是否正确")
        print("  4. 查看 test_ai_trade.log 获取完整错误信息")
        print("\n")
