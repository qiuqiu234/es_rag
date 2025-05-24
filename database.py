# database.py 修改如下
import sqlite3
from datetime import datetime
import threading

class DatabaseManager:
    def __init__(self, db_name='conversations.db'):
        self.db_name = db_name
        self.local = threading.local()  # 线程本地存储
        self._create_tables()

    def _get_conn(self):
        """获取当前线程的专属连接"""
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(
                self.db_name, 
                check_same_thread=False  # 允许跨线程访问
            )
        return self.local.conn



    def _create_tables(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # 原有建表语句保持不变
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT CHECK(role IN ('user', 'assistant')),
                content TEXT,
                timestamp DATETIME,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        ''')
        conn.commit()
        conn.close()

    def add_message(self, session_id, role, content):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (session_id, role, content, datetime.now()))
        conn.commit()

    def get_history(self, session_id, max_messages=20):
        """按时间正序获取完整对话记录"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp ASC  -- 改为正序排列
            LIMIT ?
        ''', (session_id, max_messages))
        return [{'role': row[0], 'content': row[1]} for row in cursor.fetchall()]

    def session_exists(self, session_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT 1 FROM sessions WHERE session_id = ?', 
            (session_id,)
        )
        return cursor.fetchone() is not None

    def close(self):
        """关闭所有线程的连接"""
        if hasattr(self.local, 'conn'):
            self.local.conn.close()
    
    def delete_session(self, session_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        conn.commit()

    def create_session(self, session_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # 存储为ISO格式字符串
            created_at = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO sessions (session_id, created_at)
                VALUES (?, ?)
            ''', (session_id, created_at))
            conn.commit()
        except sqlite3.IntegrityError:
            pass

    def get_all_sessions(self, limit=20):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.session_id, s.created_at, m.content 
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.session_id AND m.role = 'user'
            GROUP BY s.session_id
            ORDER BY s.created_at DESC
            LIMIT ?
        ''', (limit,))
        
        sessions = []
        for row in cursor.fetchall():
            # 转换字符串为datetime对象
            try:
                created_at = datetime.fromisoformat(row[1])
            except:
                created_at = datetime.now()
            
            sessions.append({
                "session_id": row[0],
                "created_at": created_at,
                "first_query": row[2] if row[2] else "新会话"
            })
        return sessions
