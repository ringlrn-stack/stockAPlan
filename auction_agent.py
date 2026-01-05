import tushare as ts
import pandas as pd
import os
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token")
    exit()

print("启动【盘后复盘模式】(全量 bak_daily)...")
pro = ts.pro_api(TOKEN)

def get_trading_date(offset=0):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
    try:
        cal = pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open='1')
        dates = cal.sort_values(by='cal_date', ascending=True)['cal_date'].tolist()
        return dates[offset - 1] if len(dates) >= abs(offset) else None
    except:
        return None

def get_auction_data(date_str):
    """通过 bak_daily 获取精确的竞价额 (开盘价 * 开盘量)"""
    print(f"正在拉取 {date_str} 的竞价数据...")
    try:
        # 2100积分核心权益: vol_open (开盘量)
        df = pro.bak_daily(trade_date=date_str, fields='ts_code,name,open,vol_open')
        
        if df.empty:
            print(f"警告: {date_str} 数据尚未入库或权限不足。")
            return pd.DataFrame()
        
        # 清洗数据
        df = df.dropna(subset=['open', 'vol_open'])
        
        # 计算竞价额 = Price * Volume * 100
        df['auction_amt'] = df['open'] * df['vol_open'] * 100
        return df[['ts_code', 'name', 'auction_amt']]
    except Exception as e:
        print(f"API请求失败: {e}")
        return pd.DataFrame()

def run_task():
    # 2. 确定日期
    today = get_trading_date(0)      # 今天 (1月5日)
    yesterday = get_trading_date(-1) # 上个交易日
    
    if not today or not yesterday:
        print("无法获取日历")
        return

    print(f"分析日期: {today} vs {yesterday}")

    # 3. 拉取数据 (今日和昨日都用 bak_daily，因为现在是晚上，数据已归档)
    df_today = get_auction_data(today)
    df_yest = get_auction_data(yesterday)
    
    if df_today.empty or df_yest.empty:
        print("数据获取不完整，无法计算。请确认Tushare积分是否 > 2000 且数据已更新。")
        return

    # 4. 合并计算
    # 内连接，只保留两天都有数据的股票
    merged = pd.merge(df_today, df_yest, on=['ts_code', 'name'], suffixes=('_curr', '_prev'))
    
    results = []
    for _, row in merged.iterrows():
        curr_amt = row['auction_amt_curr']
        prev_amt = row['auction_amt_prev']
        
        # 门槛 2000万
        if curr_amt >= 20000000:
            ratio = round(curr_amt / prev_amt, 2) if prev_amt > 0 else 0
            
            results.append({
                "代码": row['ts_code'],
                "名称": row['name'],
                "今日竞价(万)": round(curr_amt / 10000, 2),
                "昨日竞价(万)": round(prev_amt / 10000, 2),
                "竞昨量比": ratio
            })

    # 5. 输出
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\n✅ 成功！基于【官方归档数据】筛选出 {len(final_df)} 只股票。")
        print("提示：此结果为盘后精确复盘，明日早盘实战请切换回“混合模式”。")
    else:
        print("未发现符合条件的股票。")
        pd.DataFrame(columns=["代码", "名称"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
