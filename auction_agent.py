import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    today_str = datetime.now().strftime('%Y-%m-%d')
    print(f"任务启动: {today_str}")
    
    # 1. 获取名单 (一次抓取 500 只，确保覆盖面)
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "500", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f6", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14" 
    }
    
    try:
        resp = requests.get(list_url, params=params, timeout=10).json()
        stocks = resp['data']['diff']
        results = []

        print(f"开始精确筛选符合 2000万 门槛的股票...")

        for s in stocks:
            secid = f"{s['f13']}.{s['f12']}"
            # ndays=5 确保能获取到今天和上一个交易日的数据
            trend_url = f"https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1&fields2=f51,f56&ndays=5"
            
            try:
                t_resp = requests.get(trend_url, timeout=4).json()
                trends = t_resp['data']['trends']
                # 寻找 09:30 的集合竞价点
                auction_data = [x.split(',') for x in trends if "09:30" in x]
                
                if len(auction_data) >= 2:
                    today_val = float(auction_data[-1][1])    # 今日竞价
                    yesterday_val = float(auction_data[-2][1]) # 昨日竞价
                    
                    # --- 严格筛选：只有符合条件的才放入 results ---
                    if today_val >= 20000000:
                        ratio = round(today_val / yesterday_val, 2) if yesterday_val > 0 else 0
                        results.append({
                            "日期": today_str,
                            "代码": s['f12'], 
                            "名称": s['f14'],
                            "今日竞价(万)": round(today_val / 10000, 2),
                            "昨日竞价(万)": round(yesterday_val / 10000, 2),
                            "竞昨量比": ratio
                        })
            except:
                continue
            time.sleep(0.05)

        # --- 保存结果逻辑 ---
        if results:
            df = pd.DataFrame(results).sort_values(by="竞昨量比", ascending=False)
            print(f"筛选完成，共 {len(df)} 只股票入选。")
        else:
            # 如果没有符合条件的，创建一个只有表头的空 DataFrame
            print("今日没有股票符合竞价 > 2000万的条件。")
            df = pd.DataFrame(columns=["日期", "代码", "名称", "今日竞价(万)", "昨日竞价(万)", "竞昨量比"])

        # 保存为 Excel 和 CSV
        df.to_excel("daily_report.xlsx", index=False)
        df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        
    except Exception as e:
        print(f"程序运行出错: {e}")

if __name__ == "__main__":
    run_task()
