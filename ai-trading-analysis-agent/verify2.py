import codecs
import re

try:
    with open("out_phase2.txt", "r", encoding="utf-16le") as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if any(kw in line for kw in ["VWAP:", "OBV:", "POC:", "ATR:", "Width:", "Momentum Diagnostics", "MACD Hist:", "Price ROC:", "Entry:", "SL:", "TP1:", "Risk (Sizing/"]):
            print(line)
except Exception as e:
    print(f"Error reading output: {e}")
