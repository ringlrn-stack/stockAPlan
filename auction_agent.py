import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token，请检查 GitHub Secrets 设置")
    exit()

print(f"启动【绝对兼容模式】: 强制每分钟仅请求2次，确保100%成功...")
pro = ts.pro_api(TOKEN)

def get_trading_date(offset=0):
    """获取交易日期"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
    try:
        cal = pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open='1')
        dates = cal.sort_values(by='cal_date', ascending=True)['cal_date'].tolist()
        return dates[offset - 1] if len(dates) >= abs(offset) else None
    except:
        return None

def run_task():
    # 2. 确定日期
    today = get_trading_date(0)
    yesterday = get_trading_date(-1)
    
    if not today or not yesterday:
        print("无法获取交易日历。")
        return

    print(f"当前分析: {today} (对比 {yesterday})")

    # 3. 获取基础列表
    try:
        # 请求 1：获取列表 (消耗第1次额度)
        df_daily = pro.daily(trade_date=today, fields='ts_code,name,amount')
        
        if df_daily.empty:
            print("今日数据未出，使用昨日列表...")
            df_daily = pro.daily(trade_date=yesterday, fields='ts_code,name,amount')
            
        # 筛选前 100 只活跃股 (数量不宜过多，否则运行时间太长)
        df_daily = df_daily.sort_values(by='amount', ascending=False).head(100)
        target_codes = df_daily['ts_code'].tolist()
        print(f"已锁定 {len(target_codes)} 只股票。")
        
        # --- 安全锁 1 ---
        # 刚刚发了一次请求，现在强制休息 65 秒，把每分钟计数器归零
        print(">>> 正在冷却 API (65秒)，请耐心等待...")
        time.sleep(65)

    except Exception as e:
        print(f"获取列表失败: {e}")
        return

    results = []
    
    # 4. 龟速循环查询 (核心：绝对不触发限流)
    # 每次查 50 只，消耗 2 次请求 (今天+昨天)，然后强制睡 65 秒
    chunk_size = 50
    total_batches = (len(target_codes) + chunk_size - 1) // chunk_size
    
    for i in range(0, len(target_codes), chunk_size):
        batch_id = (i // chunk_size) + 1
        print(f"正在处理第 {batch_id}/{total_batches} 批...")
        
        chunk = target_codes[i:i+chunk_size]
        codes_str = ",".join(chunk)
        
        try:
            # 请求 A：查今天 (消耗额度 1)
            df_t = pro.stk_mins(ts_code=codes_str, start_date=f"{today} 09:30:00", end_date=f"{today} 09:30:00", freq='1min')
            
            # 请求 B：查昨天 (消耗额度 2)
            df_y = pro.stk_mins(ts_code=codes_str, start_date=f"{yesterday} 09:30:00", end_date=f"{yesterday} 09:30:00", freq='1min')
            
            # --- 核心数据处理 ---
            if not df_t.empty and not df_y.empty:
                merged = pd.merge(df_t[['ts_code', 'amount']], df_y[['ts_code', 'amount']], on='ts_code', suffixes=('_curr', '_prev'))
                
                for _, row in merged.iterrows():
                    curr_amt = row['amount_curr']
                    prev_amt = row['amount_prev']
                    
                    if curr_amt >= 20000000: # 2000万
                        name_row = df_daily[df_daily['ts_code'] == row['ts_code']]
                        name = name_row['name'].values[0] if not name_row.empty else ""
                        
                        ratio = round(curr_amt / prev_amt, 2) if prev_amt > 0 else 0
                        
                        results.append({
                            "代码": row['ts_code'],
                            "名称": name,
                            "今日竞价(万)": round(curr_amt / 10000, 2),
                            "昨日竞价(万)": round(prev_amt / 10000, 2),
                            "竞昨量比": ratio
                        })
            
            # --- 安全锁 2 ---
            # 只要还有下一批，就必须强制睡 65 秒
            if batch_id < total_batches:
                print(">>> 批次完成，强制休眠 65 秒以规避限流...")
                time.sleep(65)
                
        except Exception as e:
            print(f"批次异常: {e}")
            time.sleep(65) # 出错也要睡，防止死循环

    # 5. 结果输出
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\n任务成功完成！共筛选出 {len(final_df)} 只股票。")
    else:
        print("\n未发现符合条件的股票。")
        pd.DataFrame(columns=["代码", "名称", "今日竞价", "昨日竞价"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
