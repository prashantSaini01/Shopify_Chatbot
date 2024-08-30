from flask import Flask, render_template, request, jsonify, session
import os
import re
import uuid
import json
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai import GoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain_community.document_loaders.mongodb import MongodbLoader
from langchain.chains import create_history_aware_retriever
from langchain_core.prompts import MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
import requests
import json
from pymongo import MongoClient
import nest_asyncio
from dotenv import load_dotenv
load_dotenv()
nest_asyncio.apply()
os.environ['GOOGLE_API_KEY']
llm = GoogleGenerativeAI(
    model="gemini-1.5-pro-exp-0827",
    safety_settings={
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
)


embed_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001")



# GraphQL query to fetch product data with pagination variables
query = """
query ($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    edges {
      cursor
      node {
        id
        title
        descriptionHtml
        productType
        vendor
        variants(first: 1) {
          edges {
            node {
              priceV2 {
                amount
                currencyCode
              }
            }
          }
        }
        images(first: 1) {
          edges {
            node {
              src
            }
          }
        }
        onlineStoreUrl
      }
    }
    pageInfo {
      hasNextPage
    }
  }
}
"""

# Headers for the API request
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Storefront-Access-Token": os.getenv('ACCESS_TOKEN')
}

# MongoDB connection string

uri = os.getenv('uri')
# Connect to MongoDB
client = MongoClient(uri)
db = client['boat_Ai']
collection = db['shopify_data']

# Function to clean HTML tags from description
def clean_html_tags(text):
    clean_text = re.sub('<.*?>', '', text)
    return clean_text.strip()  # Trim whitespace

# Function to fetch product data with pagination
def fetch_products(first=50, after=None):
    variables = {'first': first, 'after': after}
    response = requests.post(os.getenv('API_ENDPOINT'), headers=headers, json={'query': query, 'variables': variables})
    return response.json()

# Fetch and store all products
products = []
cursor = None
has_next_page = True

while has_next_page:
    data = fetch_products(50, cursor)

    if 'errors' in data:
        print(f"Error: {data['errors'][0]['message']} (Code: {data['errors'][0]['extensions']['code']})")
        break

    product_edges = data['data']['products']['edges']
    for edge in product_edges:
        node = edge['node']
        variant = node['variants']['edges'][0]['node'] if node['variants']['edges'] else None
        product = {
            "product_id": node['id'],
            "product_name": node['title'],
            "product_description": clean_html_tags(node['descriptionHtml']) if node['descriptionHtml'] else None,
            "type": node['productType'],
            "vendor": node['vendor'],
            "price": variant['priceV2']['amount'] if variant else None,
            "currency": variant['priceV2']['currencyCode'] if variant else None,
            "image": node['images']['edges'][0]['node']['src'] if node['images']['edges'] else None,
            "link": node['onlineStoreUrl']
        }
        products.append(product)
        cursor = edge['cursor']

    has_next_page = data['data']['products']['pageInfo']['hasNextPage']

# Output the fetched products for verification
print(json.dumps(products, indent=4))

# Insert product data into MongoDB
if products:
    collection.insert_many(products)

print(f"Inserted {len(products)} products into MongoDB")

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

loader = MongodbLoader(
    connection_string=uri,
    db_name="boat_Ai",
    collection_name="shopify_data",
)

product_document = loader.load()

db = FAISS.from_documents(product_document, embedding=embed_model)
retriever = db.as_retriever()

contextualize_q_system_prompt = (
    "Given a chat history and the latest user question "
    "which might reference context in the chat history, "
    "formulate a standalone question which can be understood "
    "without the chat history. Do NOT answer the question, "
    "just reformulate it if needed and otherwise return it as is. "
    "Ensure the reformulated question explicitly asks for details including URLs and Image URLs where relevant."
    "and answer from context only do not answer out of context questions"
)

contextualize_q_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)
history_aware_retriever = create_history_aware_retriever(
    llm, retriever, contextualize_q_prompt
)

prompt = (
    '''You are a conversational AI specializing in product recommendations and you answer only from context provided below.
    Whenever asked about recommendations include the product URL and image URL, along with any other necessary details, and enhance the details accordingly with your knowledge but within the context.
    Use only the provided context, no external knowledge allowed.
    be a conversational mode do proper conversation
    I want to display this so while displaying imagewith size fix 200 x200 to convert it and answer the question in markdown format.
    always display image markdown as img src tag  
    and display product url as product url and on clicking that product should open
    ---Answer only through context related---
    <context>
    {context}
    </context>
'''
)
qa_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

document_chain = create_stuff_documents_chain(llm, qa_prompt)

rag_chain = create_retrieval_chain(history_aware_retriever, document_chain)

store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

conversational_rag_chain = RunnableWithMessageHistory(
    rag_chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="chat_history",
    output_messages_key="answer",
)

app = Flask(__name__)
app.secret_key = 'supersecretkey'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    if request.is_json:
        data = request.get_json()
        message = data.get('message')
        if not message:
            return jsonify({"error": "Message is required"}), 400

        # Retrieve or set a session ID
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        session_id = session['session_id']

        print("Session ID: ", session_id)

        md_response_2 = conversational_rag_chain.invoke(
            {"input": message},
            config={
                "configurable": {"session_id": session_id}
            },
        )

        print("Output:\n", md_response_2)
        response_2 = {"reply": md_response_2['answer']}
        return jsonify(response_2)
    else:
        return jsonify({"error": "Invalid input"}), 400

@app.route('/reset_chat_engine', methods=['POST'])
def reset_chat_engine():
    chat_engine_reset()
    return jsonify({"reply": "History Dumped Successfully"})

def chat_engine_reset():
    session.pop('session_id', None)
    return "History Dumped Successfully"

if __name__ == '__main__':
    app.run(debug=False)

 