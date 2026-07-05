"""
llm —— 消息面/LLM 特征层 | News & LLM feature layer
====================================================
把"公司动态(新闻/文本)"变成可用的情绪特征。真路径调 Claude,离线退词典兜底。

  provider   可插拔情绪打分器(Claude / 词典兜底)
  news       抓近期新闻
  sentiment  打分 + 严格 PIT 情绪因子

⚠️ 两条诚实前提(源自调研):
  1. LLM 只做情绪【分类】,不做涨跌【预测】—— 限制"记忆未来"作弊。
  2. 情绪因子严格 point-in-time;且免费源无历史新闻,其 alpha 暂无法回测,须过可信度层才可信。
"""

from quantmill.llm.provider import AnthropicScorer, LexiconScorer, get_scorer
from quantmill.llm.sentiment import news_sentiment, score_headlines, sentiment_feature

__all__ = [
    "get_scorer", "LexiconScorer", "AnthropicScorer",
    "score_headlines", "news_sentiment", "sentiment_feature",
]
