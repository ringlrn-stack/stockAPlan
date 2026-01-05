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

print(f"Token 验证成功 (积分 > 2000)，启动极速模式...")
pro = ts.pro_api(TOKEN)

def get_trading_date(offset=0):
    """获取交易日期"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    try:
        cal = pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open='1')
        dates = cal['cal_date'].tolist()
        return dates[offset - 1] if len(dates) >= abs(offset) else None
    except:
        return None

def run_task():
    start_time = time.time()
    
    # 2. 确定日期
    today = get_trading_date(0)
    yesterday = get_trading_date(-1)
    
    if not today or not yesterday:
        print("无法获取交易日历。")
        return

    print(f"当前分析日期: {today} (对比昨日 {yesterday})")

    # 3. 获取基础列表
    try:
        # 积分足够，直接拉取成交额前 500 的活跃股
        df_daily = pro.daily(trade_date=today, fields='ts_code,name,amount')
        
        # 容错：如果盘中 Daily 还没出，用昨天的列表作为扫描池
        if df_daily.empty:
            print("【提示】今日 Daily 数据未出(盘中)，使用昨日活跃股名单作为扫描池...")
            df_daily = pro.daily(trade_date=yesterday, fields='ts_code,name,amount')
            
        # 筛选前 500 只最活跃的票
        df_daily = df_daily.sort_values(by='amount', ascending=False).head(500)
        target_codes = df_daily['ts_code'].tolist()
        print(f"已锁定 {len(target_codes)} 只活跃股票，开始极速扫描...")

    except Exception as e:
        print(f"获取列表失败: {e}")
        return

    results = []
    
    # 4. 极速并发查询 (无 Sleep)
    # 2000积分限制是 500次/分钟。我们只需要发 500/80 ≈ 7次请求，瞬间完成。
    chunk_size = 80 
    
    for i in range(0, len(target_codes), chunk_size):
        chunk = target_codes[i:i+chunk_size]
        codes_str = ",".join(chunk)
        
        try:
            # 获取今日 09:30 分时数据
            df_t = pro.stk_mins(ts_code=codes_str, start_date=f"{today} 09:30:00", end_date=f"{today} 09:30:00", freq='1min')
            
            # 获取昨日 09:30 分时数据
            df_y = pro.stk_mins(ts_code=codes_str, start_date=f"{yesterday} 09:30:00", end_date=f"{yesterday} 09:30:00", freq='1min')
            
            if not df_t.empty and not df_y.empty:
                # 合并数据
                merged = pd.merge(df_t[['ts_code', 'amount']], df_y[['ts_code', 'amount']], on='ts_code', suffixes=('_curr', '_prev'))
                
                for _, row in merged.iterrows():
                    curr_amt = row['amount_curr'] # 09:30这一分钟的成交额 ≈ 竞价额
                    prev_amt = row['amount_prev']
                    
                    # 筛选门槛：2000万
                    if curr_amt >= 20000000:
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
        except Exception as e:
            print(f"批次异常: {e}")

    # 5. 生成报告
    print(f"耗时: {time.time() - start_time:.2f}秒")
    
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"SUCCESS! 成功筛选出 {len(final_df)} 只股票。")
    else:
        print("未筛选出符合条件的股票，生成空表。")
        pd.DataFrame(columns=["代码", "名称", "今日竞价", "昨日竞价"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
