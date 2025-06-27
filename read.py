import polars as pl

df = pl.read_csv('filtered_download_links.csv')

print(df['found_link'])