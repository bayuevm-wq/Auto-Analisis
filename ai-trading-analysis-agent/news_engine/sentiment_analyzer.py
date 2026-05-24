import logging
from typing import List

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False

logger = logging.getLogger("news_engine.analyzer")

def analyze_sentiments(texts: List[str]) -> float:
    """
    Analyze a list of news headlines/snippets.
    Returns the average compound sentiment score between -1.0 (Extreme Bearish) to 1.0 (Extreme Bullish).
    """
    if not VADER_AVAILABLE:
        logger.warning("vaderSentiment package not installed. Returning neutral 0.0.")
        return 0.0
        
    if not texts:
        return 0.0
        
    scores = []
    for text in texts:
        sentiment_dict = analyzer.polarity_scores(text)
        # We heavily rely on the 'compound' score
        comp = sentiment_dict.get('compound', 0.0)
        scores.append(comp)
        
    avg_score = sum(scores) / len(scores)
    return avg_score

if __name__ == "__main__":
    test_texts = [
        "Bitcoin ETF gets approval, institutional money floods in!",
        "Crypto exchange hacked, millions lost."
    ]
    score = analyze_sentiments(test_texts)
    print(f"Overall sentiment: {score}")
