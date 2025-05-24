from flask import Flask, request, render_template, session, redirect
import uuid
from datetime import timedelta
from database import DatabaseManager
from rag import search_documents, generate_answer

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = DatabaseManager()
   
# app.py
@app.route('/')
def index():
    # 如果已有会话ID，直接加载历史记录
    if 'session_id' in session and db.session_exists(session['session_id']):
        history = db.get_history(session['session_id'])
        return render_template('chat.html',
                            history=history,
                            sessions=db.get_all_sessions(),
                            current_query="")
    
    # 否则创建新会话
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    db.create_session(session_id)
    return render_template('chat.html',
                         history=[],
                         sessions=db.get_all_sessions(),
                         current_query="")

@app.route('/switch_session/<session_id>')
def switch_session(session_id):
    # 验证会话是否存在
    if db.session_exists(session_id):
        session['session_id'] = session_id
    else:
        session.pop('session_id', None)
    # 直接获取历史记录后渲染模板
    history = db.get_history(session_id)
    return render_template('chat.html',
                         history=history,
                         sessions=db.get_all_sessions(),
                         current_query="")

@app.route('/chat', methods=['POST'])
def chat():
    session_id = session.get('session_id')
    user_input = request.form['message']
    
    # 执行文档检索
    context_texts = search_documents(user_input)
    context = "\n".join(context_texts)
    
    # 保存用户消息（包含检索内容）
    db.add_message(session_id, 'user', user_input) 
    
    # 生成答案
    history = db.get_history(session_id)
    answer = generate_answer(user_input, context, history)
    
    # 保存助手回复
    db.add_message(session_id, 'assistant', answer)
    
    full_history = db.get_history(session_id, max_messages=10)
    
    return render_template('chat.html', 
                         history=full_history,
                         current_query=user_input,
                         search_context=context_texts)  # 新增检索内容传递

@app.route('/new_chat')
def new_chat():
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    db.create_session(session_id)
    return redirect('/')

# app.py 添加
@app.route('/delete_session/<session_id>')
def delete_session(session_id):
    # 删除会话
    db.delete_session(session_id)
    
    # 如果删除的是当前会话
    if session.get('session_id') == session_id:
        session.pop('session_id', None)
        return redirect('/')
    
    return redirect(request.referrer or '/')

if __name__ == '__main__':
    app.run(debug=False)