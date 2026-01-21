import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional
import config

class Database:
    def __init__(self, db_name: str = config.DATABASE_NAME):
        self.db_name = db_name
        # Создаем директорию если её нет
        import os
        db_dir = os.path.dirname(self.db_name)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.init_database()
    
    def get_connection(self):
        """Создает подключение к БД"""
        return sqlite3.connect(self.db_name)
    
    def init_database(self):
        """Инициализирует структуру базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица одобренных пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_date TEXT
            )
        ''')
        
        # Таблица пользователей ожидающих одобрения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                request_date TEXT
            )
        ''')
        
        # Таблица молодежных встреч
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS youth_meetings (
                meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT,
                deadline_date TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Таблица оценок (анонимные)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER,
                feedback_text TEXT,
                feedback_date TEXT,
                FOREIGN KEY (meeting_id) REFERENCES youth_meetings (meeting_id)
            )
        ''')
        
        # Таблица для отслеживания кто уже оценил (для напоминаний)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER,
                user_id INTEGER,
                has_responded INTEGER DEFAULT 0,
                reminded INTEGER DEFAULT 0,
                FOREIGN KEY (meeting_id) REFERENCES youth_meetings (meeting_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # === Работа с пользователями ===
    
    def add_pending_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Добавляет пользователя в очередь на одобрение"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO pending_users 
                (user_id, username, first_name, last_name, request_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding pending user: {e}")
            return False
        finally:
            conn.close()
    
    def get_pending_users(self) -> List[Tuple]:
        """Получает список пользователей ожидающих одобрения"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pending_users')
        users = cursor.fetchall()
        conn.close()
        return users
    
    def approve_user(self, user_id: int) -> bool:
        """Одобряет пользователя и переносит его в основную таблицу"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Получаем данные из pending
        cursor.execute('SELECT * FROM pending_users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            conn.close()
            return False
        
        # Добавляем в users
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, joined_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_data[0], user_data[1], user_data[2], user_data[3], datetime.now().isoformat()))
        
        # Удаляем из pending
        cursor.execute('DELETE FROM pending_users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        return True
    
    def reject_user(self, user_id: int) -> bool:
        """Отклоняет запрос пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_users WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    
    def is_user_approved(self, user_id: int) -> bool:
        """Проверяет одобрен ли пользователь"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def is_user_pending(self, user_id: int) -> bool:
        """Проверяет находится ли пользователь в очереди"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM pending_users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def get_all_approved_users(self) -> List[int]:
        """Получает список ID всех одобренных пользователей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    
    def remove_user(self, user_id: int) -> bool:
        """Удаляет пользователя из списка одобренных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
    
    def get_all_approved_users_info(self) -> List[Tuple]:
        """Получает информацию о всех одобренных пользователях"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, last_name FROM users ORDER BY first_name')
        users = cursor.fetchall()
        conn.close()
        return users
    
    # === Работа с молодежными встречами ===
    
    def create_meeting(self, deadline_hours: int = config.RATING_DEADLINE_HOURS) -> int:
        """Создает новую встречу и возвращает её ID"""
        from datetime import timedelta
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        start_date = datetime.now()
        deadline_date = start_date + timedelta(hours=deadline_hours)
        
        cursor.execute('''
            INSERT INTO youth_meetings (start_date, deadline_date, is_active)
            VALUES (?, ?, 1)
        ''', (start_date.isoformat(), deadline_date.isoformat()))
        
        meeting_id = cursor.lastrowid
        
        # Инициализируем user_responses для всех пользователей
        approved_users = self.get_all_approved_users()
        for user_id in approved_users:
            cursor.execute('''
                INSERT INTO user_responses (meeting_id, user_id, has_responded, reminded)
                VALUES (?, ?, 0, 0)
            ''', (meeting_id, user_id))
        
        conn.commit()
        conn.close()
        return meeting_id
    
    def get_active_meeting(self) -> Optional[int]:
        """Возвращает ID активной встречи, если есть"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT meeting_id FROM youth_meetings 
            WHERE is_active = 1 
            ORDER BY start_date DESC 
            LIMIT 1
        ''')
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def close_meeting(self, meeting_id: int):
        """Закрывает встречу"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE youth_meetings SET is_active = 0 WHERE meeting_id = ?', (meeting_id,))
        conn.commit()
        conn.close()
    
    def register_user_for_meeting(self, meeting_id: int, user_id: int):
        """Регистрирует пользователя для активной встречи (для новых пользователей)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Проверяем что пользователь еще не зарегистрирован
        cursor.execute('''
            SELECT response_id FROM user_responses 
            WHERE meeting_id = ? AND user_id = ?
        ''', (meeting_id, user_id))
        
        if not cursor.fetchone():
            # Регистрируем пользователя для этой встречи
            cursor.execute('''
                INSERT INTO user_responses (meeting_id, user_id, has_responded, reminded)
                VALUES (?, ?, 0, 0)
            ''', (meeting_id, user_id))
            conn.commit()
        
        conn.close()
    
    def get_meeting_deadline(self, meeting_id: int) -> Optional[datetime]:
        """Получает дедлайн встречи"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT deadline_date FROM youth_meetings WHERE meeting_id = ?', (meeting_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return datetime.fromisoformat(result[0])
        return None
    
    # === Работа с оценками ===
    
    def add_rating(self, meeting_id: int, user_id: int, interest: int, relevance: int, 
                   spiritual_growth: int, attended: bool):
        """Добавляет оценку (анонимно)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Добавляем оценку
        cursor.execute('''
            INSERT INTO ratings 
            (meeting_id, interest_rating, relevance_rating, spiritual_growth_rating, attended, rating_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (meeting_id, interest, relevance, spiritual_growth, 1 if attended else 0, datetime.now().isoformat()))
        
        # Отмечаем что пользователь ответил
        cursor.execute('''
            UPDATE user_responses 
            SET has_responded = 1 
            WHERE meeting_id = ? AND user_id = ?
        ''', (meeting_id, user_id))
        
        conn.commit()
        conn.close()
    
    def add_feedback(self, meeting_id: int, feedback_text: str):
        """Добавляет текстовый отзыв (анонимно)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO feedback (meeting_id, feedback_text, feedback_date)
            VALUES (?, ?, ?)
        ''', (meeting_id, feedback_text, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def mark_not_attended(self, meeting_id: int, user_id: int):
        """Отмечает что пользователь не был на встрече"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Добавляем запись с отметкой "не был"
        cursor.execute('''
            INSERT INTO ratings 
            (meeting_id, interest_rating, relevance_rating, spiritual_growth_rating, attended, rating_date)
            VALUES (?, 0, 0, 0, 0, ?)
        ''', (meeting_id, datetime.now().isoformat()))
        
        # Отмечаем что пользователь ответил
        cursor.execute('''
            UPDATE user_responses 
            SET has_responded = 1 
            WHERE meeting_id = ? AND user_id = ?
        ''', (meeting_id, user_id))
        
        conn.commit()
        conn.close()
    
    def get_meeting_stats(self, meeting_id: int) -> dict:
        """Получает статистику по встрече"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Средние оценки (только для тех кто был)
        cursor.execute('''
            SELECT 
                AVG(interest_rating) as avg_interest,
                AVG(relevance_rating) as avg_relevance,
                AVG(spiritual_growth_rating) as avg_spiritual,
                COUNT(*) as total_attended
            FROM ratings 
            WHERE meeting_id = ? AND attended = 1
        ''', (meeting_id,))
        
        stats = cursor.fetchone()
        
        # Количество не посетивших
        cursor.execute('''
            SELECT COUNT(*) FROM ratings 
            WHERE meeting_id = ? AND attended = 0
        ''', (meeting_id,))
        not_attended = cursor.fetchone()[0]
        
        # Текстовые отзывы
        cursor.execute('''
            SELECT feedback_text, feedback_date 
            FROM feedback 
            WHERE meeting_id = ?
            ORDER BY feedback_date
        ''', (meeting_id,))
        feedbacks = cursor.fetchall()
        
        conn.close()
        
        return {
            'avg_interest': round(stats[0], 2) if stats[0] else 0,
            'avg_relevance': round(stats[1], 2) if stats[1] else 0,
            'avg_spiritual_growth': round(stats[2], 2) if stats[2] else 0,
            'total_attended': stats[3] if stats[3] else 0,
            'not_attended': not_attended,
            'feedbacks': feedbacks
        }
    
    def get_users_for_reminder(self, meeting_id: int) -> List[int]:
        """Получает список пользователей для напоминания"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id FROM user_responses 
            WHERE meeting_id = ? AND has_responded = 0 AND reminded = 0
        ''', (meeting_id,))
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    
    def mark_as_reminded(self, meeting_id: int, user_id: int):
        """Отмечает что пользователю отправлено напоминание"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_responses 
            SET reminded = 1 
            WHERE meeting_id = ? AND user_id = ?
        ''', (meeting_id, user_id))
        conn.commit()
        conn.close()
    
    def get_stats_for_period(self, days: int) -> List[dict]:
        """Получает статистику за период (для графиков)"""
        from datetime import timedelta
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
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
            WHERE m.start_date >= ? AND m.is_active = 0
            GROUP BY m.meeting_id
            ORDER BY m.start_date
        ''', (cutoff_date,))
        
        results = cursor.fetchall()
        conn.close()
        
        stats = []
        for row in results:
            stats.append({
                'meeting_id': row[0],
                'date': row[1],  # Уже ISO string из базы
                'avg_interest': round(row[2], 2) if row[2] else 0,
                'avg_relevance': round(row[3], 2) if row[3] else 0,
                'avg_spiritual': round(row[4], 2) if row[4] else 0,
                'attended_count': row[5]
            })
        
        return stats
    
    def get_all_stats(self) -> List[dict]:
        """Получает всю статистику за весь период (для графиков)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
            WHERE m.is_active = 0
            GROUP BY m.meeting_id
            ORDER BY m.start_date
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        stats = []
        for row in results:
            stats.append({
                'meeting_id': row[0],
                'date': datetime.fromisoformat(row[1]).isoformat(),
                'avg_interest': round(row[2], 2) if row[2] else 0,
                'avg_relevance': round(row[3], 2) if row[3] else 0,
                'avg_spiritual': round(row[4], 2) if row[4] else 0,
                'attended_count': row[5]
            })
        
        return stats
