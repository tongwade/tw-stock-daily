import pandas as pd
import re
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.utils.dataframe import dataframe_to_rows

# 設置 matplotlib 正確顯示中文
matplotlib.rcParams['font.sans-serif'] = ['Microsoft JhengHei']  # 使用微軟正黑體
matplotlib.rcParams['axes.unicode_minus'] = False  # 正負號正常顯示

# ==========================
# 功能 1: 數據預處理
# ==========================
def preprocess_data(file_path, encoding='big5'):
    data = pd.read_csv(file_path, encoding=encoding)

    # 在 Excel 中，1,000 这种格式表示千位分隔符，实际上是文本格式，需要转换成数值格式（1000）
    data['價格'] = data['價格'].astype(str).str.replace(',', '', regex=False).astype(float)
    data['買進股數'] = data['買進股數'].astype(str).str.replace(',', '').astype(float)
    data['賣出股數'] = data['賣出股數'].astype(str).str.replace(',', '').astype(float)

    data['券商'] = data['券商'].apply(lambda x: re.sub(r'[^\u4e00-\u9fa5]', '', str(x)))
    data['買進價格'] = data['價格'] * data['買進股數']
    data['賣出價格'] = data['價格'] * data['賣出股數']
    return data

# ==========================
# 功能 2: 計算買進、賣出與買賣超
# ==========================
def calculate_buy_sell_data(data):
    buy_data = data.groupby('券商').agg(
        buy_total_qty=('買進股數', 'sum'),
        buy_total_value=('買進價格', 'sum')
    ).reset_index()
    buy_data['buy_avg_price'] = buy_data['buy_total_value'] / buy_data['buy_total_qty']
    buy_data['buy_total_qty'] /= 1000  # 轉換為張數

    sell_data = data.groupby('券商').agg(
        sell_total_qty=('賣出股數', 'sum'),
        sell_total_value=('賣出價格', 'sum')
    ).reset_index()
    sell_data['sell_avg_price'] = sell_data['sell_total_value'] / sell_data['sell_total_qty']
    sell_data['sell_total_qty'] /= 1000  # 轉換為張數

    # 計算買賣超
    buy_sell_data = pd.merge(buy_data, sell_data, on='券商', how='outer').fillna(0)
    buy_sell_data['buy_sell_diff'] = buy_sell_data['buy_total_qty'] - buy_sell_data['sell_total_qty']

    return buy_sell_data

# ==========================
# 功能 3: 排序前20名數據
# ==========================
def top_20_buy_sell(buy_sell_data):
    top_20_buy = buy_sell_data.sort_values(by='buy_total_qty', ascending=False).head(20)
    top_20_sell = buy_sell_data.sort_values(by='sell_total_qty', ascending=False).head(20)
    return top_20_buy, top_20_sell

# ==========================
# 功能 4: 雙Y軸圖表
# ==========================
def plot_dual_axis(top_20, column_qty, column_price, title, bar_color='b'):
        fig, ax1 = plt.subplots(figsize=(10, 5))
        x = top_20['券商']
        y1 = top_20[column_qty]
        y2 = top_20[column_price]

        ax1.bar(x, y1, color=bar_color, alpha=0.6, label=f'{column_qty} (張)')
        ax1.set_xlabel('券商')
        ax1.set_ylabel('股數 (張)', color=bar_color)
        ax1.tick_params(axis='y', labelcolor=bar_color)

        # 添加格線
        ax1.grid(True, axis='y', linestyle='-', alpha=1)
        ax1.grid(True, axis='x', linestyle='-', alpha=0.6)

        ax2 = ax1.twinx()
        ax2.plot(x, y2, color='black', marker='o', label=f'{column_price} (均價)')
        ax2.set_ylabel('均價', color='r')
        ax2.tick_params(axis='y', labelcolor='black')

        # 添加格線
        ax2.grid(True, axis='y', linestyle='-.', alpha=0.5)

        plt.title(title)
        ax1.set_xticks(range(len(x)))  # 設定 X 軸標籤位置
        ax1.set_xticklabels(x, rotation=45, ha='right')  # 設定標籤旋轉
        plt.tight_layout()

        return fig
# ==========================
# 功能 4.1: 新增混合圖表 (圖表三與圖表四)
# ==========================
def plot_combined_bar_line_chart(top_20, buy_col, sell_col, avg_price_col, title, buy_color, sell_color):
    fig, ax1 = plt.subplots(figsize=(10, 5))
    x = top_20['券商']
    y_buy = top_20[buy_col]
    y_sell = top_20[sell_col]
    y_avg_price = top_20[avg_price_col]

    # 左側Y軸: 買賣股數
    ax1.bar(x, y_buy, color=buy_color, alpha=0.5, label=f'{buy_col} (張)')
    ax1.bar(x, y_sell, color=sell_color, alpha=0.5, label=f'{sell_col} (張)', bottom=0)
    ax1.set_xlabel('券商')
    ax1.set_ylabel('股數 (張)')
    ax1.tick_params(axis='y', labelcolor='black')

    # 添加格線
    ax1.grid(True, axis='y', linestyle='-', alpha=1)
    ax1.grid(True, axis='x', linestyle='-', alpha=0.6)

    # 右側Y軸: 平均價格
    ax2 = ax1.twinx()
    ax2.plot(x, y_avg_price, color='black', marker='o', linestyle='-', label='均價')
    ax2.set_ylabel('均價')
    ax2.tick_params(axis='y', labelcolor='black')

    # 添加格線
    ax2.grid(True, axis='y', linestyle='-.', alpha=0.5)

    # 圖表標題與圖例
    fig.suptitle(title)
    fig.legend(loc='upper left', bbox_to_anchor=(0.1, 0.9))
    plt.xticks(rotation=45, ha='right')
    # X 軸標籤字體旋轉 45 度
    ax1.set_xticks(range(len(x)))  # 設定 X 軸標籤位置
    ax1.set_xticklabels(x, rotation=45, ha='right')  # 設定標籤旋轉

    plt.tight_layout()

    return fig

# ==========================
# 功能 4.2: 新增買賣超圖表 (圖表五與圖表六)
# ==========================
def plot_buy_sell_diff_chart(top_20_diff, title):
    fig, ax = plt.subplots(figsize=(10, 5))
    x = top_20_diff['券商']
    y = top_20_diff['buy_sell_diff']

    colors = ['red' if value > 0 else 'green' for value in y]  # 買超用紅色，賣超用綠色
    ax.bar(x, y, color=colors)
    ax.set_xlabel('券商')
    ax.set_ylabel('買賣超 (張)')
    ax.set_title(title)

    # 添加格線
    ax.grid(True, axis='y', linestyle='-', alpha=0.6)
    ax.grid(True, axis='x', linestyle='-', alpha=0.6)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig

# ==========================
# 功能 5: 保存 Excel
# ==========================
def save_to_excel_with_top20_and_diff(data, buy_sell_data, top_20_buy, top_20_sell, output_file):
    with pd.ExcelWriter(output_file) as writer:
        data.to_excel(writer, sheet_name='原始資料', index=False)
        # 排序買進資料和賣出資料
        buy_data_sorted = buy_sell_data[['券商', 'buy_total_qty', 'buy_avg_price', 'buy_sell_diff']].sort_values(by='buy_total_qty', ascending=False)
        sell_data_sorted = buy_sell_data[['券商', 'sell_total_qty', 'sell_avg_price', 'buy_sell_diff']].sort_values(by='sell_total_qty', ascending=False)

        buy_data_sorted.to_excel(writer, sheet_name='買進資料', index=False)
        sell_data_sorted.to_excel(writer, sheet_name='賣出資料', index=False)
        top_20_buy.to_excel(writer, sheet_name='買進前20', index=False)
        top_20_sell.to_excel(writer, sheet_name='賣出前20', index=False)

# ==========================
# 功能 6: 保存圖表到 Excel
# ==========================
# ==========================
# 功能 6: 保存圖表到 Excel (更新加入分析圖表)
# ==========================
def save_charts_to_excel(top_20_buy, top_20_sell, buy_sell_data, output_file):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Charts'

    # 圖表一: 買進股數前20名
    fig1 = plot_dual_axis(top_20_buy, 'buy_total_qty', 'buy_avg_price', '買進股數前20名與均價', bar_color='red')
    chart_path1 = 'top20_buy_chart.png'
    fig1.savefig(chart_path1)
    img1 = Image(chart_path1)
    sheet.add_image(img1, 'A1')

    # 圖表二: 賣出股數前20名
    fig2 = plot_dual_axis(top_20_sell, 'sell_total_qty', 'sell_avg_price', '賣出股數前20名與均價', bar_color='green')
    chart_path2 = 'top20_sell_chart.png'
    fig2.savefig(chart_path2)
    img2 = Image(chart_path2)
    sheet.add_image(img2, 'A26')

    # 圖表三: 買進股數 vs 賣出股數
    fig3 = plot_combined_bar_line_chart(top_20_buy, 'buy_total_qty', 'sell_total_qty', 'buy_avg_price',
                                        '買進股數前20名 vs 賣出股數 (張數)', 'red', 'green')
    chart_path3 = 'combined_buy_chart.png'
    fig3.savefig(chart_path3)
    img3 = Image(chart_path3)
    sheet.add_image(img3, 'R1')

    # 圖表四: 賣出股數 vs 買進股數
    fig4 = plot_combined_bar_line_chart(top_20_sell, 'sell_total_qty', 'buy_total_qty', 'sell_avg_price',
                                        '賣出股數前20名 vs 買進股數 (張數)', 'green', 'red')
    chart_path4 = 'combined_sell_chart.png'
    fig4.savefig(chart_path4)
    img4 = Image(chart_path4)
    sheet.add_image(img4, 'R26')

    # 圖表五: 買超前20名
    top_20_buy_diff = buy_sell_data.sort_values(by='buy_sell_diff', ascending=False).head(20)
    fig5 = plot_buy_sell_diff_chart(top_20_buy_diff, '買超前20名')
    chart_path5 = 'top20_buy_diff_chart.png'
    fig5.savefig(chart_path5)
    img5 = Image(chart_path5)
    sheet.add_image(img5, 'A51')

    # 圖表六: 賣超前20名
    top_20_sell_diff = buy_sell_data.sort_values(by='buy_sell_diff').head(20)
    fig6 = plot_buy_sell_diff_chart(top_20_sell_diff, '賣超前20名')
    chart_path6 = 'top20_sell_diff_chart.png'
    fig6.savefig(chart_path6)
    img6 = Image(chart_path6)
    sheet.add_image(img6, 'R51')

    workbook.save(output_file)

# ==========================
# 主程式
# ==========================
if __name__ == "__main__":
    file_path = 'C:/Users//Desktop/00693U_0529-0604.csv'
    output_file1 = 'C:/Users//Desktop/00693U_0529-0604_週報.xlsx'
    output_file2 = 'C:/Users//Desktop/00693U_0529-0604_charts.xlsx'

    data = preprocess_data(file_path)
    buy_sell_data = calculate_buy_sell_data(data)

    top_20_buy, top_20_sell = top_20_buy_sell(buy_sell_data)

    save_to_excel_with_top20_and_diff(data, buy_sell_data, top_20_buy, top_20_sell, output_file1)
    save_charts_to_excel(top_20_buy, top_20_sell, buy_sell_data, output_file2)

    print(f"數據處理完成，結果已保存到 {output_file1} 和 {output_file2}")
    print("所有圖表已嵌入第二個 Excel 檔案！")
