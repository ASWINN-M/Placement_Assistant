import pandas as pd


file_path = "attachments/Exxonmobil test shortlist.xlsx"

df = pd.read_excel(file_path)

print("Columns:")
print(df.columns.tolist())

print("\nFirst 10 rows:")
print(df.head(10).to_string(index=False))

print("\nShape:")
print(df.shape)