import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【严重错误】未读取到 Token！请检查 GitHub Secrets 设置。")
    exit()

# 打印 Token 前几位用于调试 (不打印完整的以保密)
print(f"Token 读取成功，前缀: {TOKEN[:5]}***")

pro = ts.pro_api(TOKEN)

def get_trading_date(offset=0):
    """获取交易日期"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    try:
        cal = pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open='1')
        dates = cal['cal_date'].tolist()
        return dates[offset - 1] if len(dates) >= abs(offset) else None
    except Exception as e:
        print(f"【API错误】获取日历失败: {e}")
        return None

def run_task():
    print(f"任务启动: {datetime.now()}")
    
    # 2. 确定日期
    today = get_trading_date(0)
    yesterday = get_trading_date(-1)
    print(f"正在分析日期 -> 今天: {today}, 昨天: {yesterday}")
    
    if not today or not yesterday:
        print("日期获取失败，终止。")
        return

    # 3. 获取基础列表 (改用最基础的 daily 接口，只要有积分都能调)
    print("正在拉取今日全市场行情列表...")
    try:
        # 先拉取成交额前 300 名的股票，减少请求压力
        df_daily = pro.daily(trade_date=today, fields='ts_code,name,amount')
        if df_daily.empty:
            print("【警告】今日行情列表为空！可能 Tushare 数据尚未入库，或今日是非交易日。")
            # 尝试拉取昨天的数据作为测试，防止空跑
            print("尝试切换到上一交易日数据进行测试...")
            df_daily = pro.daily(trade_date=yesterday, fields='ts_code,name,amount')
            today = yesterday # 修正日期以便测试
            
        if df_daily.empty:
            print("无法获取任何行情数据，任务终止。")
            return
            
        # 按成交额排序取前 200 只
        df_daily = df_daily.sort_values(by='amount', ascending=False).head(200)
        target_codes = df_daily['ts_code'].tolist()
        print(f"已锁定成交额前 {len(target_codes)} 只股票，开始精确查询竞价...")

    except Exception as e:
        print(f"【API错误】获取列表失败: {e}")
        return

    results = []
    
    # 4. 循环查询分钟线 (这是最稳的付费接口)
    # Tushare 单次支持 50-100 只代码，我们分批查
    chunk_size = 50
    for i in range(0, len(target_codes), chunk_size):
        chunk = target_codes[i:i+chunk_size]
        codes_str = ",".join(chunk)
        
        try:
            # 构造时间: 比如 20260105 09:30:00
            t_start = f"{today} 09:30:00"
            t_end   = f"{today} 09:30:00"
            y_start = f"{yesterday} 09:30:00"
            y_end   = f"{yesterday} 09:30:00"
            
            # 获取今日 09:30 数据
            df_t = pro.stk_mins(ts_code=codes_str, start_date=t_start, end_date=t_end, freq='1min')
            # 获取昨日 09:30 数据
            df_y = pro.stk_mins(ts_code=codes_str, start_date=y_start, end_date=y_end, freq='1min')
            
            if df_t.empty:
                print(f"批次 {i} 返回空数据，权限可能不足或数据未更新。")
                continue

            # 合并数据
            merged = pd.merge(df_t[['ts_code', 'amount']], df_y[['ts_code', 'amount']], on='ts_code', suffixes=('_curr', '_prev'))
            
            for _, row in merged.iterrows():
                curr_amt = row['amount_curr'] # 分钟线里的 amount 就是成交额
                prev_amt = row['amount_prev']
                
                # 门槛 2000万
                if curr_amt >= 20000000:
                    # 找回名称
                    name_row = df_daily[df_daily['ts_code'] == row['ts_code']]
                    name = name_row['name'].values[0] if not name_row.empty else "未知"
                    
                    ratio = round(curr_amt / prev_amt, 2) if prev_amt > 0 else 0
                    
                    results.append({
                        "代码": row['ts_code'],
                        "名称": name,
                        "今日竞价(万)": round(curr_amt / 10000, 2),
                        "昨日竞价(万)": round(prev_amt / 10000, 2),
                        "竞昨量比": ratio
                    })
            
            print(f"批次 {i} 处理完毕，当前累计入选: {len(results)} 只")
            time.sleep(0.3) # 遵守 Tushare 频率限制 (付费用户通常是每分钟几百次，这里很安全)
            
        except Exception as e:
            print(f"【API异常】在处理批次 {i} 时出错: {e}")
            time.sleep(1)

    # 5. 保存结果
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\nSUCCESS! 成功生成报告，包含 {len(final_df)} 只股票。")
    else:
        print("\n没有任何股票符合筛选条件 (或API数据获取失败)。生成空文件以防止报错。")
        pd.DataFrame(columns=["代码", "名称", "今日竞价(万)", "昨日竞价(万)", "竞昨量比"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
