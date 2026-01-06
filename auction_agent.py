import tushare as ts
import pandas as pd
import os
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token，请检查 GitHub Secrets 设置")
    exit()

print("启动【单次吞吐模式】(利用5100积分大数据量权益，规避频次限制)...")
pro = ts.pro_api(TOKEN)

def get_strategy_dates():
    """
    智能日期逻辑 (北京时间)
    """
    now_bj = datetime.now() + timedelta(hours=8)
    print(f"🕒 当前北京时间: {now_bj.strftime('%Y-%m-%d %H:%M:%S')}")

    # 获取日历
    end_str = now_bj.strftime('%Y%m%d')
    start_str = (now_bj - timedelta(days=30)).strftime('%Y%m%d')
    
    try:
        cal = pro.trade_cal(exchange='SSE', start_date=start_str, end_date=end_str, is_open='1')
        dates = cal.sort_values(by='cal_date', ascending=True)['cal_date'].tolist()
        
        if len(dates) < 3:
            return None, None, None

        # 阈值判定：09:30
        is_pre_market = now_bj.hour < 9 or (now_bj.hour == 9 and now_bj.minute < 30)

        if is_pre_market:
            print("🌙 早盘复盘模式：对比 [昨] vs [前]")
            return dates[-1], dates[-2], dates[-1]
        else:
            print("☀ 盘中实战模式：对比 [今] vs [昨]")
            # 选股基准：如果还没收盘(16点前)，今天的榜单没出，用昨天的榜单圈股票
            ref_date = dates[-2] if now_bj.hour < 16 else dates[-1]
            return dates[-1], dates[-2], ref_date

    except Exception as e:
        print(f"日期计算出错: {e}")
        return None, None, None

def run_task():
    # 2. 确定日期
    target_date, compare_date, ref_list_date = get_strategy_dates()
    if not target_date:
        print("❌ 日期获取失败")
        return

    print(f"📅 分析区间: {target_date} (最新) vs {compare_date} (基准)")

    # 3. 圈定核心股票池 (一次性圈定 500 只)
    # 这会消耗掉第 1 分钟的额度，但没关系，获取列表通常很快
    try:
        df_daily = pro.daily(trade_date=ref_list_date, fields='ts_code,name,amount')
        if df_daily.empty:
            # 容错：往前找一天
            prev_date = (datetime.strptime(ref_list_date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
            df_daily = pro.daily(trade_date=prev_date, fields='ts_code,name,amount')
        
        # 【关键点】：只取前 500 只。
        # 5100积分允许单次返回 8000 行，500 只股票 * 1 分钟 = 500 行，远远安全。
        # 即使取 800 只也没问题，为了稳妥我们取 500 龙头。
        df_daily = df_daily.sort_values(by='amount', ascending=False).head(500)
        target_codes = df_daily['ts_code'].tolist()
        print(f"✅ 已锁定核心龙头池: {len(target_codes)} 只")

    except Exception as e:
        print(f"选股池获取失败: {e}")
        return

    # 4. "一波流"拉取数据
    # 我们把 500 只股票拼成一个超长字符串，发 1 次请求
    codes_str = ",".join(target_codes)
    results = []
    
    print(f"🚀 正在发起【单次满载】请求 (500只股票 x 2个时间点)...")
    
    try:
        # 请求 1: 拿 500 只股票今天的竞价 (消耗额度 1)
        df_curr = pro.stk_mins(ts_code=codes_str, start_date=f"{target_date} 09:30:00", end_date=f"{target_date} 09:30:00", freq='1min')
        
        # 请求 2: 拿 500 只股票昨天的竞价 (消耗额度 2)
        df_prev = pro.stk_mins(ts_code=codes_str, start_date=f"{compare_date} 09:30:00", end_date=f"{compare_date} 09:30:00", freq='1min')
        
        # --- 任务结束！我们只用了2次请求，完美规避限制 ---
        
        if not df_curr.empty and not df_prev.empty:
            # 数据合并与计算
            merged = pd.merge(df_curr[['ts_code', 'amount']], df_prev[['ts_code', 'amount']], on='ts_code', suffixes=('_curr', '_prev'))
            
            for _, row in merged.iterrows():
                curr_amt = row['amount_curr']
                prev_amt = row['amount_prev']
                
                # 门槛 2000万
                if curr_amt >= 20000000:
                    name_row = df_daily[df_daily['ts_code'] == row['ts_code']]
                    name = name_row['name'].values[0] if not name_row.empty else ""
                    
                    ratio = round(curr_amt / prev_amt, 2) if prev_amt > 0 else 0
                    
                    results.append({
                        "代码": row['ts_code'],
                        "名称": name,
                        "数据日期": target_date,
                        "今日竞价(万)": round(curr_amt / 10000, 2),
                        "昨日竞价(万)": round(prev_amt / 10000, 2),
                        "竞昨量比": ratio
                    })
    except Exception as e:
        print(f"❌ 数据拉取异常: {e}")
        # 如果这里报错，通常是因为网络超时（一次拉太多），但500只通常在2秒内返回

    # 5. 保存
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\n🎉 任务成功！耗时极短，共筛选出 {len(final_df)} 只股票。")
        print("💡 备注：此方案利用了您5100积分的大数据量吞吐能力，在2次请求内完成了所有工作。")
    else:
        print("\n未发现符合条件的股票 (或数据尚未生成)。")
        pd.DataFrame(columns=["代码"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
