import tushare as ts
import pandas as pd
import os
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token，请检查 GitHub Secrets 设置")
    exit()

print("启动【智能复盘模式】(自动判断早/晚班)...")
pro = ts.pro_api(TOKEN)

def get_target_dates():
    """
    智能日期逻辑：
    - 如果当前是 17:00 之前 -> 假设今日数据未出 -> 取 [上个交易日] 为最新，[上上个] 为对比
    - 如果当前是 17:00 之后 -> 假设今日数据已出 -> 取 [今天] 为最新，[上个交易日] 为对比
    """
    now = datetime.now()
    # 注意：GitHub Actions 默认时区是 UTC，这里需要+8小时转为北京时间
    # 如果你本地运行已经是北京时间，可以去掉 + timedelta(hours=8)
    # 为了保险，我们直接用 pytz 或者简单硬编码加8小时（假设服务器是UTC）
    # 但为了简单通用，这里假设 machine time 就是北京时间，或者我们只看相对逻辑
    # 如果你在 GitHub Actions 跑，建议加上下面这行修正时区：
    now_bj = now + timedelta(hours=8) 
    
    print(f"当前系统时间(修正后): {now_bj}")

    if now_bj.hour < 17:
        print("🕒 当前时间早于 17:00，切换为【复盘模式】：抓取上个交易日数据...")
        # 基准日回退 1 天
        base_date = now_bj - timedelta(days=1)
    else:
        print("🕔 当前时间晚于 17:00，切换为【收盘模式】：抓取今日最新数据...")
        base_date = now_bj

    base_str = base_date.strftime('%Y%m%d')
    start_str = (base_date - timedelta(days=60)).strftime('%Y%m%d')

    try:
        # 获取交易日历 (is_open='1' 剔除周末节假日)
        cal = pro.trade_cal(exchange='SSE', start_date=start_str, end_date=base_str, is_open='1')
        dates = cal.sort_values(by='cal_date', ascending=True)['cal_date'].tolist()
        
        if len(dates) < 2:
            print("❌ 无法获取足够的历史交易日信息")
            return None, None
            
        # dates[-1] 是基准截止日（即我们逻辑上的“最新日”）
        # dates[-2] 是对比日
        target_today = dates[-1]
        target_yesterday = dates[-2]
        
        return target_today, target_yesterday

    except Exception as e:
        print(f"日期计算出错: {e}")
        return None, None

def get_auction_data(date_str):
    """通过 bak_daily 获取精确的竞价额"""
    print(f"📡 正在拉取 {date_str} 的竞价数据...")
    try:
        # 2100积分权益: vol_open (开盘量)
        df = pro.bak_daily(trade_date=date_str, fields='ts_code,name,open,vol_open')
        
        if df.empty:
            print(f"⚠️ 警告: {date_str} 数据为空 (可能非交易日或权限/数据未更新)")
            return pd.DataFrame()
        
        df = df.dropna(subset=['open', 'vol_open'])
        # 计算竞价额 = 开盘价 * 开盘量 * 100
        df['auction_amt'] = df['open'] * df['vol_open'] * 100
        return df[['ts_code', 'name', 'auction_amt']]
    except Exception as e:
        print(f"API请求失败: {e}")
        return pd.DataFrame()

def run_task():
    # 2. 智能确定日期
    target_date, compare_date = get_target_dates()
    
    if not target_date or not compare_date:
        print("无法确定分析日期，任务终止。")
        return

    print(f"📅 锁定分析区间: 最新[{target_date}] vs 对比[{compare_date}]")

    # 3. 拉取数据 (使用最稳的 bak_daily)
    df_curr = get_auction_data(target_date)
    df_prev = get_auction_data(compare_date)
    
    if df_curr.empty or df_prev.empty:
        print("数据不完整，无法计算量比。")
        # 生成空表防报错
        pd.DataFrame(columns=["代码", "名称"]).to_excel("daily_report.xlsx")
        return

    # 4. 合并计算
    merged = pd.merge(df_curr, df_prev, on=['ts_code', 'name'], suffixes=('_curr', '_prev'))
    
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
                "数据日期": target_date, # 增加一列显示数据日期，防止混淆
                "今日竞价(万)": round(curr_amt / 10000, 2),
                "昨日竞价(万)": round(prev_amt / 10000, 2),
                "竞昨量比": ratio
            })

    # 5. 输出
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\n✅ 成功！基于[{target_date}]数据筛选出 {len(final_df)} 只股票。")
    else:
        print("\n未发现符合条件的股票。")
        pd.DataFrame(columns=["代码", "名称"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
