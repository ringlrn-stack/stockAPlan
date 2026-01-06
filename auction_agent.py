import tushare as ts
import pandas as pd
import os
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token，请检查 GitHub Secrets 设置")
    exit()

print("启动【全市场扫描版】(抛弃 daily，利用 stock_basic + stk_auction)...")
pro = ts.pro_api(TOKEN)

def get_now_bj():
    """获取北京时间"""
    return datetime.utcnow() + timedelta(hours=8)

def get_market_dates_by_status(base_date_str):
    """日历状态递归判断"""
    print(f"📅 检查日历状态: {base_date_str}")
    try:
        df = pro.trade_cal(exchange='SSE', start_date=base_date_str, end_date=base_date_str)
        if df.empty: return None, None
        
        row = df.iloc[0]
        if row['is_open'] == 1:
            return base_date_str, row['pretrade_date']
        else:
            # 递归找前一交易日
            return get_market_dates_by_status(row['pretrade_date'])
    except:
        return None, None

def get_strategy_dates():
    """日期策略"""
    now_bj = get_now_bj()
    print(f"🕒 当前北京时间: {now_bj.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 09:30 前强制复盘昨日
    if now_bj.hour < 9 or (now_bj.hour == 9 and now_bj.minute < 30):
        input_date = (now_bj - timedelta(days=1)).strftime('%Y%m%d')
        print("🌙 盘前模式：基准日设为昨天")
    else:
        input_date = now_bj.strftime('%Y%m%d')
        print("☀ 盘中模式：基准日设为今天")
        
    return get_market_dates_by_status(input_date)

def get_all_stock_codes():
    """
    【替代 daily 的关键】
    使用 stock_basic 获取全市场股票代码和名称
    """
    print("📋 正在拉取全市场股票列表 (stock_basic)...")
    try:
        # 只取上市状态(L)的股票
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        return df
    except Exception as e:
        print(f"股票列表获取失败: {e}")
        return pd.DataFrame()

def get_auction_data_batch(date_str, stock_list):
    """
    stk_auction 批量拉取
    由于是全市场扫描，我们将 chunk_size 设为 500 (5100积分单次限制大，但分批更稳)
    """
    print(f"📥 全扫描 {date_str} 竞价数据...")
    all_df = []
    
    # stock_list 是一个 list of ts_code
    chunk_size = 800 # 5100积分可以适当加大单次量
    
    for i in range(0, len(stock_list), chunk_size):
        chunk = stock_list[i:i+chunk_size]
        codes_str = ",".join(chunk)
        try:
            df = pro.stk_auction(ts_code=codes_str, trade_date=date_str)
            if not df.empty:
                all_df.append(df)
        except:
            pass
            
    if all_df:
        return pd.concat(all_df)
    return pd.DataFrame()

def run_task():
    # 2. 确定日期
    target_date, compare_date = get_strategy_dates()
    if not target_date: return

    print(f"📅 锁定区间: {target_date} vs {compare_date}")

    # 3. 获取全市场基础信息 (不使用 daily)
    df_basics = get_all_stock_codes()
    if df_basics.empty: return
    
    all_codes = df_basics['ts_code'].tolist()
    print(f"✅ 全市场共 {len(all_codes)} 只股票，准备开始地毯式扫描...")

    # 4. 拉取竞价数据
    # 这里会把全市场几千只股票的数据都拉回来，5100积分大概需要 10-20 秒
    df_curr = get_auction_data_batch(target_date, all_codes)
    df_prev = get_auction_data_batch(compare_date, all_codes)
    
    if df_curr.empty:
        print(f"❌ {target_date} 数据暂未生成或获取失败")
        return

    # 5. 计算逻辑
    print("🚀 数据清洗与计算...")
    
    # stk_auction 可能返回多条记录（极其罕见），我们按 ts_code 分组求和 amount 确保安全
    df_curr_agg = df_curr.groupby('ts_code')['amount'].sum().reset_index().rename(columns={'amount': 'amt_curr'})
    df_prev_agg = df_prev.groupby('ts_code')['amount'].sum().reset_index().rename(columns={'amount': 'amt_prev'})
    
    # 合并
    merged = pd.merge(df_curr_agg, df_prev_agg, on='ts_code', how='inner')
    
    # 关联中文名称 (从 stock_basic 来的 df_basics)
    merged = pd.merge(merged, df_basics[['ts_code', 'name']], on='ts_code', how='left')
    
    results = []
    for _, row in merged.iterrows():
        curr_amt = row['amt_curr']
        prev_amt = row['amt_prev']
        
        # 门槛 2000万
        if curr_amt >= 20000000:
            ratio = round(curr_amt / prev_amt, 2) if prev_amt > 0 else 0
            
            results.append({
                "代码": row['ts_code'],
                "名称": row['name'], # 这里用的就是 stock_basic 的名字
                "日期": target_date,
                "今日竞价(万)": round(curr_amt / 10000, 2),
                "昨日竞价(万)": round(prev_amt / 10000, 2),
                "竞昨量比": ratio
            })

    # 6. 保存
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\n🎉 扫描完成！全市场共筛选出 {len(final_df)} 只竞价爆量股。")
    else:
        print("\n未发现符合条件的股票。")
        pd.DataFrame(columns=["代码"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
