import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 获取 GitHub Secrets 中的 Token
TOKEN = os.getenv("91dba4a6bb22fc1b9970ae8005d5746a5120a0a652cc7df80fea8469")
# 如果你是本地测试，请手动把 Token 填在下面：
# TOKEN = "你的_Tushare_Token_粘贴在这里"

if not TOKEN:
    raise ValueError("未找到 Tushare Token，请在 GitHub Secrets 中配置！")

pro = ts.pro_api(TOKEN)

def get_trading_date(offset=0):
    """获取最近的交易日（自动处理周末和节假日）"""
    # 获取过去 20 天的交易日历
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=20)).strftime('%Y%m%d')
    
    cal = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date, is_open='1')
    trade_dates = cal['cal_date'].tolist()
    
    # -1 代表最后一个交易日（即“今天”或“最近收盘日”）
    # -2 代表上一个交易日
    try:
        return trade_dates[offset - 1]
    except:
        return None

def run_task():
    print(f"任务启动: {datetime.now()}")
    
    # 1. 确定日期：今天（或最近交易日）和昨天（上个交易日）
    today_date = get_trading_date(0)   # 今天
    yesterday_date = get_trading_date(-1) # 昨天
    
    print(f"正在获取数据... 今日: {today_date}, 昨日对比: {yesterday_date}")
    
    if not today_date or not yesterday_date:
        print("无法获取交易日历，任务终止。")
        return

    # 2. 获取全市场“开盘成交额”
    # Tushare 的 daily 接口非常快，直接请求全市场
    # 'amount' 是全天成交额，'open' 是开盘价
    # 为了精准获取“竞价成交额”，我们可以使用 'stk_mins' (1分钟线) 的 09:30 数据
    # 或者，如果你的积分足够，直接用 'bak_daily' (备用行情) 里面有精准的 'vol_open' (开盘量)
    
    # 这里我们使用最通用的方案：直接请求今日的 1分钟线 (需要一定积分权限)
    # 为了节省积分和请求次数，我们先拉取一个基础列表，只查活跃股
    
    # --- 方案 A：使用每日行情接口 (Daily) 近似计算 ---
    # 大多数付费用户都有 daily 权限。
    # 开盘金额 ≈ 开盘价 * 开盘量 (注：Daily接口通常不给专门的开盘量，只给全天量)
    
    # --- 方案 B (推荐)：使用分钟线接口 (stk_mins) ---
    # 这是最准的。我们需要循环请求，所以先筛选。
    
    # 先拿今日全市场基础行情，按金额排序取前 200 只
    df_daily = pro.daily(trade_date=today_date, fields='ts_code,name,amount')
    if df_daily.empty:
        print("今日行情未更新（可能尚未收盘或积分不足），尝试获取实时快照...")
        # 注意：Tushare 盘中实时接口需要更高权限，建议盘后复盘使用
        # 如果必须盘中跑，此处需换回 requests 方式，但既然你付了费，建议用 Tushare 的 snapshot
        return

    # 筛选前 300 名活跃股进行精细查询
    df_daily = df_daily.sort_values(by='amount', ascending=False).head(300)
    target_codes = df_daily['ts_code'].tolist()
    
    results = []
    print(f"开始通过专业接口获取 {len(target_codes)} 只股票的精准竞价数据...")

    # Tushare 支持批量获取分钟线，我们分批请求，每次 50 只
    # 格式: 000001.SZ
    chunk_size = 50
    for i in range(0, len(target_codes), chunk_size):
        chunk = target_codes[i:i+chunk_size]
        codes_str = ",".join(chunk)
        
        try:
            # 获取今日 09:30 的分钟线
            df_today_min = pro.stk_mins(ts_code=codes_str, start_date=f"{today_date} 09:30:00", end_date=f"{today_date} 09:30:00", freq='1min')
            # 获取昨日 09:30 的分钟线
            df_yest_min = pro.stk_mins(ts_code=codes_str, start_date=f"{yesterday_date} 09:30:00", end_date=f"{yesterday_date} 09:30:00", freq='1min')
            
            # 合并数据
            # 1分钟线的 amount 就是该分钟的成交额，即竞价+开盘瞬间，非常接近真实竞价
            merged = pd.merge(df_today_min[['ts_code', 'amount']], df_yest_min[['ts_code', 'amount']], on='ts_code', suffixes=('_today', '_yest'))
            
            for _, row in merged.iterrows():
                today_val = row['amount_today']
                yest_val = row['amount_yest']
                
                # 门槛 2000万
                if today_val >= 20000000:
                    ratio = round(today_val / yest_val, 2) if yest_val > 0 else 0
                    # 找回名字
                    name = df_daily[df_daily['ts_code'] == row['ts_code']]['name'].values[0]
                    
                    results.append({
                        "代码": row['ts_code'],
                        "名称": name,
                        "今日竞价(万)": round(today_val / 10000, 2),
                        "昨日竞价(万)": round(yest_val / 10000, 2),
                        "竞昨量比": ratio
                    })
        except Exception as e:
            print(f"API 请求异常: {e}")
            time.sleep(1) # Tushare 也有频率限制，稍微歇一下
            
    # 保存结果
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"报告生成成功！共筛选出 {len(final_df)} 只股票。")
    else:
        print("无符合条件股票。")
        pd.DataFrame(columns=["代码", "名称", "今日竞价(万)", "昨日竞价(万)", "竞昨量比"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
