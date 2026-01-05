import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    print(f"任务启动时间: {datetime.now()}")
    
    # 1. 直接获取当前成交额前 500 名的个股
    # 9:30分时，这里的成交额(f6)其实就是集合竞价成交额
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "500", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f6", # 按成交额排序
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14,f6" 
    }
    
    try:
        resp = requests.get(list_url, params=params, timeout=10).json()
        stocks = resp['data']['diff']
        
        results = []
        print(f"成功获取候选名单，开始精确解析前 {len(stocks)} 只股票的历史数据...")

        for s in stocks:
            secid = f"{s['f13']}.{s['f12']}"
            # ndays=5 确保跨越周末和元旦
            trend_url = f"https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1&fields2=f51,f56&ndays=5"
            
            try:
                t_data = requests.get(trend_url, timeout=5).json()
                trends = t_data.get('data', {}).get('trends', [])
                
                # 寻找每天 09:30 的数据点
                # trends 里的数据格式通常是 "日期 时间,成交额,..."
                open_points = [x.split(',') for x in trends if "09:30" in x]
                
                if len(open_points) >= 2:
                    # 获取最近两次的 09:30 数据
                    # open_points[-1] 是今天，open_points[-2] 是上一个交易日
                    today_val = float(open_points[-1][1])
                    yesterday_val = float(open_points[-2][1])
                    
                    if today_val >= 20000000: # 门槛：2000万
                        ratio = round(today_val / yesterday_val, 2) if yesterday_val > 0 else 0
                        results.append({
                            "代码": s['f12'], "名称": s['f14'],
                            "今日竞价(万)": round(today_val / 10000, 2),
                            "昨日竞价(万)": round(yesterday_val / 10000, 2),
                            "竞昨量比": ratio
                        })
            except:
                continue
            
            # 这里的 sleep 很有必要，防止 9:30 抢数据时被东财封 IP
            if len(results) % 50 == 0 and len(results) > 0:
                time.sleep(0.1)

        # 2. 生成报告
        if results:
            final_df = pd.DataFrame(results).sort_values(by="竞昨量比", ascending=False)
            final_df.to_excel("daily_report.xlsx", index=False)
            print(f"报告已生成，筛选出 {len(final_df)} 只符合条件的股票。")
        else:
            # 如果真的没有任何股票达标，创建一个只有表头的空文件，避免 Actions 报错
            pd.DataFrame(columns=["代码", "名称", "今日竞价(万)", "昨日竞价(万)", "竞昨量比"]).to_excel("daily_report.xlsx", index=False)
            print("今日暂无符合‘竞价 > 2000万’条件的股票。")

    except Exception as e:
        print(f"运行出错: {e}")

if __name__ == "__main__":
    run_task()
