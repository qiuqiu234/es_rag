import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
from PyPDF2 import PdfReader
from openai import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from database import DatabaseManager

# 加载环境变量
load_dotenv()

# 初始化Elasticsearch客户端
es = Elasticsearch(
    hosts=[os.getenv("ELASTIC_HOST")],
    verify_certs=False,
    basic_auth=("elastic", "y5WsPMDr6f==QqgtDtw2")
)
print("正在检查Elasticsearch连接...")
if not es.ping():
    raise ConnectionError("无法连接到Elasticsearch")
else:
    print("Elasticsearch连接成功")

# 初始化E5多语言嵌入模型
print("正在初始化嵌入模型")
embedding_model = SentenceTransformer('intfloat/multilingual-e5-small',device='cpu')
print("初始化嵌入模型成功")

# 初始化DeepSeek客户端
print("初始化DeepSeek客户端")
deepseek_client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)
print("初始化DeepSeek成功")

def process_document(file_path):
    """支持多格式文档处理"""
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == '.pdf':
            return process_pdf(file_path)
        elif ext == '.docx':
            return process_docx(file_path)
        elif ext in ['.txt', '.md']:
            return process_text(file_path)
        elif ext == '.xlsx':
            return process_excel(file_path)
        else:
            raise ValueError(f"不支持的文档格式: {ext}")
    except Exception as e:
        print(f"处理文档 {file_path} 失败: {str(e)}")
        return ""

def process_pdf(file_path):
    """处理PDF文件"""
    text = ""
    reader = PdfReader(file_path)
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def process_docx(file_path):
    """处理Word文档"""
    doc = doc.Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs])

def process_text(file_path):
    """处理文本类文件（txt/md）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def process_excel(file_path):
    """处理Excel文档"""
    try:
        import pandas as pd
        
        # 读取Excel文件
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # 提取三列数据并格式化成文本
        formatted_text = []
        for _, row in df.iterrows():
            entry = f"日期：{row['DeclareDate']}\n标题：{row['Title']}\n内容：{row['NewsContent']}\n"
            formatted_text.append(entry)
        
        return "\n\n".join(formatted_text)
        
    except Exception as e:
        print(f"处理Excel文件时出错: {str(e)}")
        return ""

def chunk_text(text):
    """使用递归字符分割器进行文本分块"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=50,
        separators = [
        "\n\n",        # 段落分隔
        "\n",          # 换行
        "。|!|！|\\?|？",  # 句子结束
        ";|；",        # 分号
        ",|，",        # 逗号
        "\\s+"        # 空格
    ]
    )
    return text_splitter.split_text(text)

def create_index():
    """创建Elasticsearch索引"""
    try:
        if not es.indices.exists(index="rag"):
            es.indices.create(
                index="rag",
                mappings={
                    "properties": {
                        "text": {"type": "text"},
                        "embedding": {
                            "type": "dense_vector",
                            "dims": 384,
                            "index": True,
                            "similarity": "cosine"
                        }
                    }
                }
            )
            print("索引创建成功")
        else:
            print("索引已存在")
    except Exception as e:
        print(f"索引创建失败: {str(e)}")
        raise

def index_documents(file_paths):
    """处理并索引文档"""
    create_index()
    
    for file_path in file_paths:
        text = process_document(file_path)
        chunks = chunk_text(text)
        
        for chunk in chunks:
            # 添加passage前缀并生成嵌入
            prefixed_text = f"passage: {chunk}"
            embedding = embedding_model.encode(prefixed_text)
            
            doc = {
                "text": chunk,
                "embedding": embedding.tolist()
            }
            es.index(index="rag", document=doc)


def search_documents(query, k=3):
    """执行语义搜索"""
    # 添加query前缀并生成嵌入
    prefixed_query = f"query: {query}"
    query_embedding = embedding_model.encode(prefixed_query).tolist()
    
    response = es.search(
        index="rag",
        knn={
            "field": "embedding",
            "query_vector": query_embedding,
            "k": k,
            "num_candidates": 100
        },
        source=["text"]
    )
    return [hit["_source"]["text"] for hit in response["hits"]["hits"]]


def generate_answer(query, context):
    """使用DeepSeek生成答案"""
    system_prompt = """你是一个专业的AI助手，请根据以下上下文信息回答问题。
如果上下文信息不足以回答问题，禁止用其他信息回答问题，请严格回答我不知道。"""
    
    user_content = f"上下文信息：\n{context}\n\n问题：{query}"
    
    full_response = []
    
    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3,
            stream=False  
        )
        return response.choices[0].message.content
        
    except Exception as e:
        return f"生成答案时发生错误：{str(e)}"

# def generate_answer(query, context):
#     """使用DeepSeek生成答案"""
#     system_prompt = """你是一个专业的AI助手，请根据以下上下文信息回答问题。
# 如果上下文信息不足以回答问题，请严格回答我不知道。"""
    
#     user_content = f"上下文信息：\n{context}\n\n问题：{query}"
    
#     full_response = []

#     response = deepseek_client.chat.completions.create(
#         model="deepseek-chat",
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_content}
#         ],
#         temperature=0.3,
#         stream=True
#     )
#         # 实时处理流式响应
#     for chunk in response:
#         delta_content = chunk.choices[0].delta.content
#         if delta_content:
#             print(delta_content, end="", flush=True)
#             full_response.append(delta_content)
#     return "".join(full_response)



    # 其他方法保持不变...
# 示例使用流程
if __name__ == "__main__":
    # # 索引文档
    #index_documents(["2022.xlsx"])
    
    # 查询示例
    user_query = "为我推荐一款3000元以内的百炼手机"
    
    # 语义搜索
    context_texts = search_documents(user_query)
    context = "\n".join(context_texts)
    
    # 生成答案
    print(f"问题：{user_query}")
    final_answer = generate_answer(user_query, context)

#多轮对话

db = DatabaseManager()

def generate_answer(query, context, history=None):
    """支持历史对话的答案生成"""
    system_prompt = """你是一个专业的AI助手，请根据以下上下文信息和历史会话回答问题。
如果上下文信息和历史会话不足以回答问题，禁止用其他信息回答问题，请严格回答我不知道。
    
上下文：
{context}

历史对话：
{history}

如果信息不足，请回答我不知道。"""
    
    # 格式化历史对话
    history_text = "\n".join(
        [f"{msg['role']}: {msg['content']}" 
         for msg in history] if history else []
    )
    
    user_content = f"问题：{query}"
    
    response = deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt.format(
                context=context, 
                history=history_text
            )},
            {"role": "user", "content": user_content}
        ],
        temperature=0.3,
        stream=False
    )
    
    return response.choices[0].message.content