import pandas as pd
from data_engine.market_data import fetch_ohlcv
from feature_engine.feature_extractor import generate_features

df = fetch_ohlcv("BTCUSDT", "4h", limit=100)
df, features = generate_features(df)
print(f"ROC Price: {features['roc_price']}")
print(f"ROC Momentum: {features['roc_momentum']}")
print(df[['close', 'roc_price', 'roc_momentum']].tail(15))
