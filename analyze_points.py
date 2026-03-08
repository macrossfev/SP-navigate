import pandas as pd
import numpy as np

df = pd.read_excel('output/water_sampling/tsp/plan_summary_tsp.xlsx')

print('=== 长寿区 82 个采样点分布分析 ===\n')
print('地理分布:')
print(f'  经度：{df["经度"].min():.4f} - {df["经度"].max():.4f}')
print(f'  纬度：{df["纬度"].min():.4f} - {df["纬度"].max():.4f}\n')

lng_span = (df['经度'].max() - df['经度'].min()) * 85
lat_span = (df['纬度'].max() - df['纬度'].min()) * 111
print(f'分布范围:')
print(f'  东西：约{lng_span:.1f}km')
print(f'  南北：约{lat_span:.1f}km\n')

center_lng = df['经度'].mean()
center_lat = df['纬度'].mean()
print(f'中心点：{center_lng:.4f}, {center_lat:.4f}\n')

def simple_dist(lat1, lng1, lat2, lng2):
    return np.sqrt((lat1-lat2)**2 * 111**2 + (lng1-lng2)**2 * 85**2)

df['dist'] = df.apply(lambda r: simple_dist(r['纬度'], r['经度'], center_lat, center_lng), axis=1)

print(f'距中心距离:')
print(f'  平均：{df["dist"].mean():.1f}km')
print(f'  最远：{df["dist"].max():.1f}km')
print(f'  最近：{df["dist"].min():.1f}km\n')

print('=== 前 13 个点位 ===')
for i, row in df.head(13).iterrows():
    print(f'{i+1}. {row["地址"][:30]}')
    print(f'   坐标：{row["经度"]:.4f}, {row["纬度"]:.4f} | 距中心：{row["dist"]:.1f}km')
