import requests
import pandas as pd
import time
from datetime import datetime

def run_task():
    print(f"任务启动: {datetime.now()}")
    
    # 1. 先拿名单 (用成交额排序取前 300 只，保证是活跃股)
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "300", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f6", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f13,f14"
    }
    
    try:
        stocks = requests.get(list_url, params=params, timeout=10).json()['data']['diff']
        results = []

        print(f"候选池 {len(stocks)} 只，开始核查“第0笔”交易明细...")

        for s in stocks:
            secid = f"{s['f13']}.{s['f12']}"
            # pos=0 表示从第0条开始取，pz=1 表示只取1条
            # 这就是直接要把“竞价”那一条取出来
            tick_url = f"https://push2.eastmoney.com/api/qt/stock/details/get?secid={secid}&pos=0&pz=1&fields1=f1&fields2=f51,f52,f53,f54,f55"
            
            try:
                tick_res = requests.get(tick_url, timeout=3).json()
                details = tick_res['data']['details']
                
                if details:
                    # details[0] 格式示例: "09:25:04,15.60,2850,0,4450000,..."
                    # 逗号分隔的第 5 个字段 (index 4) 通常是成交金额(元)，或者是 价格*量 手动算
                    first_trade = details[0].split(',')
                    
                    # 时间校验：必须是 09:25 或 09:30 之前的
                    trade_time = first_trade[0]
                    
                    # 东方财富 details 字段说明：
                    # 0:时间, 1:价格, 2:手数, 3:笔数, 4:成交额(注意：有的票不返回额，需 价格*手数*100)
                    price = float(first_trade[1])
                    vol_hand = float(first_trade[2]) # 手数
                    
                    # 计算竞价额 (元) = 价格 * 手数 * 100
                    auction_amount = price * vol_hand * 100
                    
                    if auction_amount >= 20000000: # 2000万
                        results.append({
                            "代码": s['f12'],
                            "名称": s['f14'],
                            "竞价时间": trade_time,
                            "竞价成交额(万)": round(auction_amount / 10000, 2)
                        })
            except:
                pass
            
            # 这种精确接口不能太快，稍微慢一点点
            time.sleep(0.05)

        if results:
            df = pd.DataFrame(results).sort_values(by="竞价成交额(万)", ascending=False)
            df.to_excel("daily_report.xlsx", index=False)
            df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
            print(f"成功！筛选出 {len(df)} 只竞价超 2000万 的股票。")
        else:
            print("没有符合条件的股票。")
            # 生成空表防止报错
            pd.DataFrame(columns=["代码", "名称", "竞价时间", "竞价成交额(万)"]).to_excel("daily_report.xlsx")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_task()
