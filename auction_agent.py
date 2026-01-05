import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 1. 验证 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未设置 Token")
    exit()

print(f"Token 验证成功，启用 2100 积分极速模式...")
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
        print("无法获取日期，任务终止。")
        return
    
    print(f"当前分析: {today} (对比 {yesterday})")

    # 3. 获取候选池
    try:
        # 2100积分权限：直接拉取全市场数据毫无压力
        # 我们扩大范围，扫描成交额前 500 名的活跃股
        df_daily = pro.daily(trade_date=today, fields='ts_code,name,amount')
        
        # 容错：如果盘中 daily 没出，用昨天的列表做候选池（Tushare daily通常收盘后出）
        if df_daily.empty:
            print("注意：今日Daily数据未出(盘中)，使用昨日活跃股名单作为扫描池...")
            df_daily = pro.daily(trade_date=yesterday, fields='ts_code,name,amount')
            today_for_list = yesterday
        else:
            today_for_list = today
            
        # 筛选前 500 只最活跃的票
        df_daily = df_daily.sort_values(by='amount', ascending=False).head(500)
        target_codes = df_daily['ts_code'].tolist()
        print(f"候选池锁定: {len(target_codes)} 只股票")

    except Exception as e:
        print(f"获取列表失败: {e}")
        return

    results = []
    
    # 4. 极速并发查询
    # 你的积分支持单次请求更多数据，且不需要 sleep
    chunk_size = 80 # 每次查 80 只 (加大批次)
    
    for i in range(0, len(target_codes), chunk_size):
        chunk = target_codes[i:i+chunk_size]
        codes_str = ",".join(chunk)
        
        try:
            # 获取今日 09:30
            # 注意：stk_mins 是实时更新的，9:31 就能取到 9:30 的数据
            df_t = pro.stk_mins(ts_code=codes_str, start_date=f"{today} 09:30:00", end_date=f"{today} 09:30:00", freq='1min')
            
            # 获取昨日 09:30
            df_y = pro.stk_mins(ts_code=codes_str, start_date=f"{yesterday} 09:30:00", end_date=f"{yesterday} 09:30:00", freq='1min')
            
            if not df_t.empty and not df_y.empty:
                # 合并计算
                merged = pd.merge(df_t[['ts_code', 'amount']], df_y[['ts_code', 'amount']], on='ts_code', suffixes=('_curr', '_prev'))
                
                for _, row in merged.iterrows():
                    curr_amt = row['amount_curr']
                    prev_amt = row['amount_prev']
                    
                    if curr_amt >= 20000000: # 2000万门槛
                        # 从 df_daily 找回中文名
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
            # 2100分很稳，基本不会报错，除非网络抖动
            
    # 5. 输出报告
    print(f"耗时: {time.time() - start_time:.2f}秒")
    
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"成功筛选出 {len(final_df)} 只股票，报告已生成。")
    else:
        print("无符合条件数据，生成空表。")
        pd.DataFrame(columns=["代码", "名称", "今日竞价", "昨日竞价"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
