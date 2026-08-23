# ParcelPilot Customer Support Assistant

An AI-powered customer support assistant for ParcelPilot, a B2B logistics platform.

The assistant helps customers with orders, cancellations, service credits, tickets, account information, policies, and support SLAs using the supplied ParcelPilot data pack.

The main design goal is reliable answers from verified data rather than allowing the LLM to make decisions on its own.

## Problem Statement

ParcelPilot support teams need to search across:

- Customer agreements
- Support policies and SOPs
- Product documentation
- Account, order, and ticket data

The assistant brings these sources together and answers customer questions using the supplied data.

When information is insufficient, access is restricted, or an action requires human confirmation, the system handles the situation without guessing.

## Architecture
User
  |
  v
Streamlit Chat Interface
  |
  v
Deterministic Orchestrator
  |
  +--------------------------+
  |                          |
  v                          v
Intent / Entity          Evidence Assembly
Detection                    |
                             +--> Account / Order / Ticket Data
                             |
                             +--> Semantic Document Retrieval
                             |
                             +--> Access Control
                             |
                             +--> Business Calculations
                             |
                             v
                      Verified Evidence
                             |
                    +--------+--------+
                    |                 |
                    v                 v
              Deterministic      One LLM Call
                Response          if needed
                    |                 |
                    +--------+--------+
                             |
                             v
                       Final Response

The LLM is not responsible for the overall orchestration. The application first determines what information is required, retrieves it, validates access, and builds the evidence package.

**##When Does the LLM Get Called?**

The LLM is mainly used for natural-language response generation.

Examples:

Cross-account access → 0 calls
Missing/insufficient evidence → 0 calls
Escalation preparation → 0 calls
Escalation confirmation → 0 calls
Normal grounded question → 1 call

##Three Separations

The system keeps three responsibilities separate:

1. Retrieval

Find relevant information from the supplied documents and structured data.

2. Decision Making

Apply deterministic access controls, business rules, calculations, and source-authority rules.

3. Response Generation

Use the LLM only to turn verified evidence into a clear customer-facing response.

**#Source Authority**

Not every source is treated equally.

The system distinguishes between:

Current support policies
Current SOPs
Customer-specific agreements
Product documentation
Historical or deprecated material

Customer-specific agreements can override general policies where applicable.

Deprecated documents are excluded from active retrieval.

Historical support information is treated as context rather than unquestioned truth.

**#Access Control**

The chatbot uses a mocked logged-in customer context.

Customer data is scoped at the data and retrieval layer rather than relying only on the LLM prompt.

A customer cannot access another customer's:

Orders
Tickets
Account information
Customer-specific agreements

For example, a Northstar customer asking about a LumenWorks order is denied without making an LLM call.

**#Tools / Capabilities**

The system supports three main capability categories
1)Document Retrieval

Searches policies, agreements, SOPs, and product documentation using semantic retrieval.

2)Structured Data

Works with account, order, and ticket information and performs business calculations such as cancellation fees, service credits, and SLA checks.

3)State-Changing Actions

The system can prepare and create support escalations.

Actions require explicit confirmation before execution.

Example:

User: Please escalate this issue.

Assistant:
I can prepare an escalation with priority P2.
Would you like me to proceed?

User: Yes.

Assistant:
Escalation created successfully.

**#Intent Detection**

Common intents are detected without an LLM call, including:

Order questions
Cancellation
Service credits
SLA questions
Ticket questions
Account questions
Escalation requests

Relevant entities such as order IDs, ticket IDs, and severity can also be extracted deterministically.

**#Semantic Retrieval**

The document knowledge base is converted into chunks and embedded using:

sentence-transformers/all-MiniLM-L6-v2

FAISS is used for vector similarity search.

Retrieved documents are then filtered and ranked according to account scope, topic, and source authority.

**#Time Handling**

Time-based reasoning uses the dataset snapshot time provided by the ParcelPilot data pack rather than the machine's current time.

This keeps SLA and operational decisions consistent with the supplied assessment dataset.

**#Documented Assumption**

Authentication is mocked through the customer selector in the Streamlit sidebar.

The selected customer represents the currently logged-in account.

This allows the access-control behavior to be demonstrated without implementing a production authentication system.

Example Questions
Cancellation:
Can Northstar cancel ORD-1001 without a cancellation fee?
>Service Credit:
A pickup is three hours late because of carrier fault. Should I get a service credit?
>Account Data:
Show me my recent orders.
>Ticket:
What is the status of my support ticket?
>Access Control:
What is the status of ORD-2001?

If ORD-2001 belongs to another account, the system refuses to expose it.

>Escalation:
Please escalate this issue.

The system asks for confirmation before creating the escalation

**#Tech Stack:**

Frontend:
Streamlit

Language:
Python

LLM:
Gemini API

Retrieval:
Sentence Transformers,FAISS

Data:
Pandas, Excel workbookPDF, knowledge base

Testing :Pytest

**#Project Structure:**
parcelpilot/
│
├── app.py
├── config.py
├── requirements.txt
├── README.md
│
├── data/
│   ├── ParcelPilot_Assessment_Data.xlsx
│   └── knowledge_base/
│
├── scripts/
│   ├── build_index.py
│   └── check_environment.py
│
├── src/
│   ├── actions/
│   ├── agent/
│   ├── data/
│   ├── embeddings/
│   ├── ingestion/
│   ├── retrieval/
│   └── security/
│
├── tests/
│
└── vectorstore/
    ├── index.faiss
    ├── metadata.pkl
    └── embedder.json

## Run Locally

### 1. Clone the repository

git clone <your-repository-url>
cd parcelpilot

### 2. Create a virtual environment

Windows:

python -m venv .venv
.venv\Scripts\Activate.ps1

### 3. Install dependencies

pip install -r requirements.txt

### 4. Configure the API key

Create a `.env` file in the project root:

GEMINI_API_KEY=your_api_key_here

Do not commit `.env` to GitHub.

### 5. Run the application

streamlit run app.py

The application will be available at:

http://localhost:8501

# ParcelPilot Customer Support Assistant

An AI-powered customer support assistant for ParcelPilot, a B2B logistics platform.

## 🚀 Live Demo

**[Try the ParcelPilot Customer Support Assistant](https://parcelpilot-ai-support-assistant-aakzwubjetfacmrektwq93.streamlit.app/)**

Hosted on Streamlit Community Cloud.

**#Author:**
Rushikesh Desale
Artificial Intelligence and Data Science Graduate'26 | 
