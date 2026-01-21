import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.database_url = config.DATABASE_URL
        self.init_database()

    def get_connection(self):
        """Создает подключение к БД"""
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)

    def init_database(self):
        """Инициализирует структуру базы данных"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Таблица одобренных пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        joined_date TEXT
                    )
                ''')

                # Таблица пользователей ожидающих одобрения
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pending_users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        request_date TEXT
                    )
                ''')

                # Таблица молодежных встреч
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS youth_meetings (
                        meeting_id SERIAL PRIMARY KEY,
                        start_date TEXT,
                        deadline_date TEXT,
                        is_active INTEGER DEFAULT 1
                    )
                ''')

                # Таблица оценок (анонимные)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ratings (
                        rating_id SERIAL PRIMARY KEY,
                        meeting_id INTEGER,
                        interest_rating INTEGER,
                        relevance_rating INTEGER,
                        spiritual_growth_rating INTEGER,
                        attended INTEGER,
                        rating_date TEXT,
                        FOREIGN KEY (meeting_id) REFERENCES youth_meetings (meeting_id)
                    )
                ''')

                # Таблица текстовых отзывов (анонимные)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS feedback (
                        feedback_id SERIAL PRIMARY KEY,
                        meeting_id INTEGER,
                        feedback_text TEXT,
                        feedback_date TEXT,
                        FOREIGN KEY (meeting_id) REFERENCES youth_meetings (meeting_id)
                    )
                ''')

                # Таблица для отслеживания кто уже оценил (для напоминаний)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_responses (
                        response_id SERIAL PRIMARY KEY,
                        meeting_id INTEGER,
                        user_id BIGINT,
                        has_responded INTEGER DEFAULT 0,
                        reminded INTEGER DEFAULT 0,
                        FOREIGN KEY (meeting_id) REFERENCES youth_meetings (meeting_id)
                    )
                ''')

                conn.commit()
        logger.info("Database tables created/verified")

    # === Работа с пользователями ===

    def add_pending_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Добавляет пользователя в очередь на одобрение"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO pending_users
                        (user_id, username, first_name, last_name, request_date)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        request_date = EXCLUDED.request_date
                    ''', (user_id, username, first_name, last_name, datetime.now().isoformat()))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding pending user: {e}")
            return False

    def get_pending_users(self) -> List[Tuple]:
        """Получает список пользователей ожидающих одобрения"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT user_id, username, first_name, last_name, request_date FROM pending_users')
                rows = cursor.fetchall()
                return [(row['user_id'], row['username'], row['first_name'], row['last_name'], row['request_date']) for row in rows]

    def approve_user(self, user_id: int) -> bool:
        """Одобряет пользователя и переносит его в основную таблицу"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Получаем данные из pending
                    cursor.execute('SELECT * FROM pending_users WHERE user_id = %s', (user_id,))
                    user_data = cursor.fetchone()

                    if not user_data:
                        return False

                    # Добавляем в users
                    cursor.execute('''
                        INSERT INTO users
                        (user_id, username, first_name, last_name, joined_date)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        joined_date = EXCLUDED.joined_date
                    ''', (user_data['user_id'], user_data['username'], user_data['first_name'],
                          user_data['last_name'], datetime.now().isoformat()))

                    # Удаляем из pending
                    cursor.execute('DELETE FROM pending_users WHERE user_id = %s', (user_id,))

                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error approving user: {e}")
            return False

    def reject_user(self, user_id: int) -> bool:
        """Отклоняет запрос пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('DELETE FROM pending_users WHERE user_id = %s', (user_id,))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error rejecting user: {e}")
            return False

    def is_user_approved(self, user_id: int) -> bool:
        """Проверяет одобрен ли пользователь"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
                result = cursor.fetchone()
                return result is not None

    def is_user_pending(self, user_id: int) -> bool:
        """Проверяет находится ли пользователь в очереди"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT user_id FROM pending_users WHERE user_id = %s', (user_id,))
                result = cursor.fetchone()
                return result is not None

    def get_all_approved_users(self) -> List[int]:
        """Получает список ID всех одобренных пользователей"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT user_id FROM users')
                rows = cursor.fetchall()
                return [row['user_id'] for row in rows]

    # === Работа с молодежными встречами ===

    def create_meeting(self, deadline_hours: int = config.RATING_DEADLINE_HOURS) -> int:
        """Создает новую встречу и возвращает её ID"""
        start_date = datetime.now()
        deadline_date = start_date + timedelta(hours=deadline_hours)

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO youth_meetings (start_date, deadline_date, is_active)
                    VALUES (%s, %s, 1)
                    RETURNING meeting_id
                ''', (start_date.isoformat(), deadline_date.isoformat()))

                meeting_id = cursor.fetchone()['meeting_id']

                # Инициализируем user_responses для всех пользователей
                approved_users = self.get_all_approved_users()
                for user_id in approved_users:
                    cursor.execute('''
                        INSERT INTO user_responses (meeting_id, user_id, has_responded, reminded)
                        VALUES (%s, %s, 0, 0)
                    ''', (meeting_id, user_id))

                conn.commit()
        return meeting_id

    def get_active_meeting(self) -> Optional[int]:
        """Возвращает ID активной встречи, если есть"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT meeting_id FROM youth_meetings
                    WHERE is_active = 1
                    ORDER BY start_date DESC
                    LIMIT 1
                ''')
                result = cursor.fetchone()
                return result['meeting_id'] if result else None

    def close_meeting(self, meeting_id: int):
        """Закрывает встречу"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('UPDATE youth_meetings SET is_active = 0 WHERE meeting_id = %s', (meeting_id,))
                conn.commit()

    def get_meeting_deadline(self, meeting_id: int) -> Optional[datetime]:
        """Получает дедлайн встречи"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT deadline_date FROM youth_meetings WHERE meeting_id = %s', (meeting_id,))
                result = cursor.fetchone()
                if result:
                    return datetime.fromisoformat(result['deadline_date'])
                return None

    # === Работа с оценками ===

    def add_rating(self, meeting_id: int, user_id: int, interest: int, relevance: int,
                   spiritual_growth: int, attended: bool):
        """Добавляет оценку (анонимно)"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Добавляем оценку
                cursor.execute('''
                    INSERT INTO ratings
                    (meeting_id, interest_rating, relevance_rating, spiritual_growth_rating, attended, rating_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (meeting_id, interest, relevance, spiritual_growth, 1 if attended else 0, datetime.now().isoformat()))

                # Отмечаем что пользователь ответил
                cursor.execute('''
                    UPDATE user_responses
                    SET has_responded = 1
                    WHERE meeting_id = %s AND user_id = %s
                ''', (meeting_id, user_id))

                conn.commit()

    def add_feedback(self, meeting_id: int, feedback_text: str):
        """Добавляет текстовый отзыв (анонимно)"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO feedback (meeting_id, feedback_text, feedback_date)
                    VALUES (%s, %s, %s)
                ''', (meeting_id, feedback_text, datetime.now().isoformat()))
                conn.commit()

    def mark_not_attended(self, meeting_id: int, user_id: int):
        """Отмечает что пользователь не был на встрече"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Добавляем запись с отметкой "не был"
                cursor.execute('''
                    INSERT INTO ratings
                    (meeting_id, interest_rating, relevance_rating, spiritual_growth_rating, attended, rating_date)
                    VALUES (%s, 0, 0, 0, 0, %s)
                ''', (meeting_id, datetime.now().isoformat()))

                # Отмечаем что пользователь ответил
                cursor.execute('''
                    UPDATE user_responses
                    SET has_responded = 1
                    WHERE meeting_id = %s AND user_id = %s
                ''', (meeting_id, user_id))

                conn.commit()

    def get_meeting_stats(self, meeting_id: int) -> dict:
        """Получает статистику по встрече"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Средние оценки (только для тех кто был)
                cursor.execute('''
                    SELECT
                        AVG(interest_rating) as avg_interest,
                        AVG(relevance_rating) as avg_relevance,
                        AVG(spiritual_growth_rating) as avg_spiritual,
                        COUNT(*) as total_attended
                    FROM ratings
                    WHERE meeting_id = %s AND attended = 1
                ''', (meeting_id,))

                stats = cursor.fetchone()

                # Количество не посетивших
                cursor.execute('''
                    SELECT COUNT(*) as cnt FROM ratings
                    WHERE meeting_id = %s AND attended = 0
                ''', (meeting_id,))
                not_attended = cursor.fetchone()['cnt']

                # Текстовые отзывы
                cursor.execute('''
                    SELECT feedback_text, feedback_date
                    FROM feedback
                    WHERE meeting_id = %s
                    ORDER BY feedback_date
                ''', (meeting_id,))
                feedbacks = [(row['feedback_text'], row['feedback_date']) for row in cursor.fetchall()]

                return {
                    'avg_interest': round(float(stats['avg_interest']), 2) if stats['avg_interest'] else 0,
                    'avg_relevance': round(float(stats['avg_relevance']), 2) if stats['avg_relevance'] else 0,
                    'avg_spiritual_growth': round(float(stats['avg_spiritual']), 2) if stats['avg_spiritual'] else 0,
                    'total_attended': stats['total_attended'] if stats['total_attended'] else 0,
                    'not_attended': not_attended,
                    'feedbacks': feedbacks
                }

    def get_users_for_reminder(self, meeting_id: int) -> List[int]:
        """Получает список пользователей для напоминания"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT user_id FROM user_responses
                    WHERE meeting_id = %s AND has_responded = 0 AND reminded = 0
                ''', (meeting_id,))
                return [row['user_id'] for row in cursor.fetchall()]

    def mark_as_reminded(self, meeting_id: int, user_id: int):
        """Отмечает что пользователю отправлено напоминание"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    UPDATE user_responses
                    SET reminded = 1
                    WHERE meeting_id = %s AND user_id = %s
                ''', (meeting_id, user_id))
                conn.commit()

    def get_stats_for_period(self, days: int) -> List[dict]:
        """Получает статистику за период (для графиков)"""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT
                        m.meeting_id,
                        m.start_date,
                        AVG(CASE WHEN r.attended = 1 THEN r.interest_rating END) as avg_interest,
                        AVG(CASE WHEN r.attended = 1 THEN r.relevance_rating END) as avg_relevance,
                        AVG(CASE WHEN r.attended = 1 THEN r.spiritual_growth_rating END) as avg_spiritual,
                        COUNT(CASE WHEN r.attended = 1 THEN 1 END) as attended_count
                    FROM youth_meetings m
                    LEFT JOIN ratings r ON m.meeting_id = r.meeting_id
                    WHERE m.start_date >= %s AND m.is_active = 0
                    GROUP BY m.meeting_id, m.start_date
                    ORDER BY m.start_date
                ''', (cutoff_date,))

                results = cursor.fetchall()

                stats = []
                for row in results:
                    stats.append({
                        'meeting_id': row['meeting_id'],
                        'date': datetime.fromisoformat(row['start_date']),
                        'avg_interest': round(float(row['avg_interest']), 2) if row['avg_interest'] else 0,
                        'avg_relevance': round(float(row['avg_relevance']), 2) if row['avg_relevance'] else 0,
                        'avg_spiritual': round(float(row['avg_spiritual']), 2) if row['avg_spiritual'] else 0,
                        'attended_count': row['attended_count']
                    })

                return stats
