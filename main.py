import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from news_analyzer import NewsAnalyzer
from bybit_manager import BybitManager

# Загрузка переменных окружения
load_dotenv()

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
BYBIT_API_KEY = os.getenv('BYBIT_API_KEY', '')
BYBIT_API_SECRET = os.getenv('BYBIT_API_SECRET', '')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 20))  # 20 секунд по умолчанию

class CryptoNewsBot:
    def __init__(self):
        self.telegram_bot = Bot(token=TELEGRAM_TOKEN)
        self.news_analyzer = NewsAnalyzer()
        self.bybit_manager = BybitManager(BYBIT_API_KEY, BYBIT_API_SECRET)
        self.tracked_coins = {}
        self.last_news = {}
        self.startup_sent = False
        
    async def get_futures_coins_from_bybit(self):
        """Получить список всех фьючерс-пар с Bybit"""
        try:
            coins = await self.bybit_manager.get_futures_pairs()
            logger.info(f"Получено {len(coins)} фьючерс-пар с Bybit")
            return coins
        except Exception as e:
            logger.error(f"Ошибка при получении фьючерс-пар: {e}")
            return []
    
    async def check_news_for_coin(self, coin_symbol: str, coin_name: str):
        """Проверить новости для конкретной монеты"""
        try:
            # Получить новости из всех источников
            all_news = await self.news_analyzer.get_news_from_all_sources(coin_name)
            
            if not all_news:
                return None
            
            # Анализировать новости
            impact_score, summary, sources_found = await self.news_analyzer.analyze_impact(
                coin_name, 
                all_news
            )
            
            # Проверить, новая ли это новость
            news_hash = hash(summary)
            if coin_symbol in self.last_news and self.last_news[coin_symbol] == news_hash:
                return None
            
            self.last_news[coin_symbol] = news_hash
            
            # Если влияние значительное, отправить уведомление
            if impact_score >= 5:
                await self.send_notification(
                    coin_symbol, 
                    coin_name, 
                    impact_score, 
                    summary, 
                    sources_found
                )
                
            return {
                'coin': coin_symbol,
                'impact_score': impact_score,
                'summary': summary,
                'sources': sources_found
            }
            
        except Exception as e:
            logger.error(f"Ошибка при проверке новостей для {coin_symbol}: {e}")
            return None
    
    async def send_notification(self, coin_symbol: str, coin_name: str, 
                               impact_score: int, summary: str, sources: str):
        """Отправить уведомление в Telegram"""
        try:
            # Определить эмодзи в зависимости от влияния
            if impact_score >= 9:
                emoji = "🔴🔴🔴"
            elif impact_score >= 8:
                emoji = "🔴🔴"
            elif impact_score >= 7:
                emoji = "🔴"
            elif impact_score >= 6:
                emoji = "🟠"
            else:
                emoji = "🟡"
            
            # Получить текущую цену
            price_info = await self.bybit_manager.get_coin_price(coin_symbol)
            price_text = f"\n💵 Цена: ${price_info}" if price_info > 0 else ""
            
            message = f"""{emoji} *КРИТИЧЕСКАЯ НОВОСТЬ: {coin_symbol}*

💰 Монета: {coin_name}
📊 Уровень влияния: *{impact_score}/10*{price_text}

📰 *Новость:*
{summary}

🔗 *Источники:*
{sources}

🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            
            await self.telegram_bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"✅ Уведомление отправлено для {coin_symbol} (влияние: {impact_score}/10)")
            
        except TelegramError as e:
            logger.error(f"Ошибка Telegram при отправке уведомления: {e}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")
    
    async def send_startup_message(self):
        """Отправить сообщение о запуске"""
        try:
            if not self.startup_sent:
                message = """
✅ *Крипто Ньюс Бот запущен!*

📊 *Режим работы:*
• Все фьючерсы Bybit
• Проверка каждые 20 секунд
• Анализ новостей из всех источников
• Оценка влияния до 10 баллов
• Уведомления при влиянии ≥ 5 баллов

🔗 *Источники новостей:*
• CoinTelegraph RSS
• CryptoPanic API
• CoinMarketCap
• Reddit r/cryptocurrency
• Twitter/X криптовалютные каналы
• CoinGecko API
• Криптовалютные блоги

⚠️ Получите уведомление при важных новостях!
"""
                await self.telegram_bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=message,
                    parse_mode='Markdown'
                )
                self.startup_sent = True
                logger.info("✅ Стартовое сообщение отправлено")
        except Exception as e:
            logger.error(f"Ошибка при отправке стартового сообщения: {e}")
    
    async def run(self):
        """Основной цикл бота"""
        logger.info("🤖 Крипто Ньюс Бот запущен!")
        
        await self.send_startup_message()
        
        iteration = 0
        while True:
            try:
                iteration += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"Итерация #{iteration} - {datetime.now().strftime('%H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                # Получить список всех фьючерс-пар
                futures_pairs = await self.get_futures_coins_from_bybit()
                
                if not futures_pairs:
                    logger.warning("Не удалось получить список фьючерс-пар, повторяем...")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue
                
                # Проверить новости для каждой пары параллельно
                tasks = []
                for pair in futures_pairs:
                    tasks.append(
                        self.check_news_for_coin(pair['symbol'], pair['name'])
                    )
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Обработка результатов
                detected = []
                for result in results:
                    if isinstance(result, dict) and result is not None:
                        detected.append(result)
                    elif isinstance(result, Exception):
                        logger.error(f"Ошибка в задаче: {result}")
                
                if detected:
                    logger.info(f"\n🔔 Обнаружено {len(detected)} новостей с влиянием ≥ 5:")
                    for news in detected:
                        logger.info(f"   • {news['coin']}: влияние {news['impact_score']}/10")
                else:
                    logger.info("ℹ️ Значимых новостей не обнаружено")
                
                logger.info(f"⏳ Следующая проверка через {CHECK_INTERVAL} сек...")
                await asyncio.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("🛑 Бот остановлен пользователем")
                break
            except Exception as e:
                logger.error(f"💥 Критическая ошибка в основном цикле: {e}")
                await asyncio.sleep(5)

async def main():
    bot = CryptoNewsBot()
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")