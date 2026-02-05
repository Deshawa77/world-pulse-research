import pandas as pd

def clean_data(df):
    # Drop duplicates
    df = df.drop_duplicates()
    # Remove missing values
    df = df.dropna()
    return df
